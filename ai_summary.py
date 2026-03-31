"""
SearXNG AI Summary Plugin — Secure GET Edition
================================================
Security model:
  - Browser sends GET /ai_summary?q=<query> — query string only
  - post_search() hook caches SearXNG's own results in memory (keyed by query)
  - GET endpoint reads from that cache — client never supplies result data
  - No internal HTTP calls, no bot detection issues

CONFIGURATION (settings.yml)
------------------------------
  plugins:
    searx.plugins.ai_summary.SXNGPlugin:
      active: true

  ai_summary:
    base_url:        "http://127.0.0.1:1234/v1"
    api_key:         "lm-studio"
    model:           "google/gemma-3-1b"
    model_more:      "openai/gpt-oss-20b"
    max_results:     5
    max_tokens:      300
    max_tokens_more: 800
    timeout:         60
"""

import json
import logging
import os
import sqlite3
import threading
import time
import typing as t

import httpx
from flask_babel import gettext as _
from searx import get_setting
from searx.plugins import Plugin, PluginCfg, PluginInfo

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Request
    from searx.search import SearchWithPlugins

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    """ You are a helpful assistant embedded in a search engine.
    The user searched for a query and you are given the top search results.
    Write a concise, factual summary (3-5 sentences) that directly answers
    the query using the provided results.
    Do NOT start with "Based on the results" or "The search results say" or "The user is asking for" or "The user is attempting to" or "The provided search results offer" similar meta-phrases.
    Do NOT use markdown formatting.
    If the results are unrelated to the query, say you could not find a clear answer."""
)

_DEFAULT_PROMPT_MORE = (
    """ You are a helpful assistant in a search engine.
    Return ONLY valid JSON — no markdown fences, no explanation, just raw JSON.
    Use exactly this shape:
    {"overview": "2-3 sentence intro paragraph",
    "sections": [
     {"title": "Section Title",
      "items": [
        {"type": "text", "value": "A plain bullet point"},
        {"type": "code", "lang": "bash", "value": "the command or code here"}
      ]}
     ],
     "follow_up": ["Follow-up question 1?", "Follow-up question 2?", "Follow-up question 3?"]}
     Rules:
     - Use 2-4 sections with 2-5 items each.
    - Use type "text" for the vast majority of items — plain factual bullet points.
    - ONLY use type "code" when the item IS an actual programming command or shell command
     that a developer would literally run in a terminal. Examples of when to use code:
    "sudo apt install apache2", "git clone https://...", "npm install".
     - NEVER use type "code" for: URLs, website addresses, phone numbers, addresses,
    schedules, prices, names, quotes, or any plain information — use type "text" instead.
     - Keep follow_up to exactly 3 questions.
     - Return ONLY the JSON object. Nothing else."""
)


def _setting(key: str, default=None):
    return get_setting(f"ai_summary.{key}", default)


def _read(result, key: str) -> str:
    try:
        val = getattr(result, key, None)
        if val is not None:
            return str(val)
        if hasattr(result, "get"):
            val = result.get(key)
            if val is not None:
                return str(val)
    except Exception:
        pass
    return ""


# ── Result cache ──────────────────────────────────────────────────────────────
# post_search() stores results here keyed by query (lowercase stripped).
# GET endpoints read from here — client never supplies result data.
# Entries expire after 5 minutes to avoid unbounded memory growth.

_cache: dict = {}          # {"query": {"results": [...], "ts": float}}
_cache_lock = threading.Lock()
_CACHE_TTL  = 300          # seconds
_CACHE_MAX  = 500          # maximum number of cached entries


def _cache_set(query: str, results: list):
    key = query.lower().strip()
    with _cache_lock:
        # Evict entries older than TTL
        now = time.time()
        expired = [k for k, v in list(_cache.items()) if now - v["ts"] > _CACHE_TTL]
        for k in expired:
            del _cache[k]
        # Enforce maximum cache size — evict oldest entry if at capacity
        if key not in _cache and len(_cache) >= _CACHE_MAX:
            oldest = min(_cache, key=lambda k: _cache[k]["ts"])
            del _cache[oldest]
        _cache[key] = {"results": results, "ts": now}


def _cache_get(query: str) -> list:
    key = query.lower().strip()
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry["ts"] < _CACHE_TTL:
            return entry["results"]
    return []


# ── Persistent summary cache (SQLite) ─────────────────────────────────────────
# Stores completed LLM-generated summaries keyed by (query_key, type).
# Survives container restarts — DB file lives in the volume-mounted /etc/searxng.
# Distinct from _cache above, which stores raw search results (short-lived, in-memory).

_db_lock = threading.Lock()
_DB_PATH_DEFAULT = "/etc/searxng/ai_summary_cache.db"
_db_path: str = _DB_PATH_DEFAULT


def _db_init(path: str) -> None:
    global _db_path
    _db_path = path
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS summary_cache (
                        query_key  TEXT NOT NULL,
                        type       TEXT NOT NULL,
                        content    TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        PRIMARY KEY (query_key, type)
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_created "
                    "ON summary_cache(created_at)"
                )
                conn.commit()
        logger.info("ai_summary: persistent summary cache at %s", path)
    except Exception as exc:
        logger.warning("ai_summary: could not initialise summary cache: %s", exc)


def _db_enabled() -> bool:
    return bool(_setting("response_cache_enabled", True))


def _db_get(query: str, cache_type: str) -> "str | None":
    if not _db_enabled():
        return None
    key = query.lower().strip()
    ttl = float(_setting("response_cache_ttl", 604800))
    try:
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                row = conn.execute(
                    "SELECT content, created_at FROM summary_cache "
                    "WHERE query_key=? AND type=?",
                    (key, cache_type),
                ).fetchone()
        if row and (time.time() - row[1]) < ttl:
            logger.info(
                "ai_summary: cache hit (%s) for %r (age %.0fs)",
                cache_type, query, time.time() - row[1],
            )
            return row[0]
        return None
    except Exception as exc:
        logger.warning("ai_summary db_get error: %s", exc)
        return None


def _db_set(query: str, cache_type: str, content: str) -> None:
    if not _db_enabled() or not content:
        return
    key = query.lower().strip()
    try:
        with _db_lock:
            with sqlite3.connect(_db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO summary_cache "
                    "(query_key, type, content, created_at) VALUES (?,?,?,?)",
                    (key, cache_type, content, time.time()),
                )
                conn.commit()
        logger.info("ai_summary: cached %s summary for %r", cache_type, query)
    except Exception as exc:
        logger.warning("ai_summary db_set error: %s", exc)


# ── LLM streaming ─────────────────────────────────────────────────────────────

def _build_prompt(query: str, results: list) -> str:
    lines = [f'Search query: "{query}"\n\nTop results:\n']
    for i, r in enumerate(results, 1):
        title   = r.get("title", "")   if isinstance(r, dict) else _read(r, "title")
        url     = r.get("url", "")     if isinstance(r, dict) else _read(r, "url")
        content = r.get("content", "") if isinstance(r, dict) else _read(r, "content")
        lines.append(f"{i}. {title} ({url})\n   {content}\n")
    lines.append("\nAnswer based on the results above.")
    return "\n".join(lines)


def _stream_llm(query: str, results: list, model: str,
                max_tokens: int, system_prompt: str):
    base_url    = _setting("base_url")
    api_key     = _setting("api_key", "no-key")
    timeout     = float(_setting("timeout", 60))
    max_results = int(_setting("max_results", 5))

    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers  = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model":       model,
        "max_tokens":  max_tokens,
        "temperature": 0.3,
        "stream":      True,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": _build_prompt(query, results[:max_results])},
        ],
    }

    with httpx.stream("POST", endpoint, headers=headers,
                      json=payload, timeout=timeout) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if raw == "[DONE]":
                return
            try:
                chunk = json.loads(raw)
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


class SXNGPlugin(Plugin):
    """Secure AI summary — client sends query only, server uses its own results."""

    id = "ai_summary"
    keywords: list = []

    def __init__(self, plg_cfg: "PluginCfg") -> None:
        super().__init__(plg_cfg)
        self.info = PluginInfo(
            id=self.id,
            name=_("AI Summary"),
            description=_("Show an AI-generated summary above search results"),
            preference_section="general",
        )

    def init(self, app) -> bool:
        # Initialise persistent summary cache — file lives in the volume-mounted searxng/ dir
        _db_init(_setting("response_cache_path", _DB_PATH_DEFAULT))

        from flask import request as freq, Response, stream_with_context

        # ── Compact summary endpoint ─────────────────────────────────────
        _MAX_QUERY_LEN = 500

        @app.route("/ai_summary", methods=["GET"])
        def ai_summary_api():
            query = freq.args.get("q", "").strip()[:_MAX_QUERY_LEN]
            if not query:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            model         = _setting("model")
            max_tokens    = int(_setting("max_tokens", 300))
            system_prompt = _DEFAULT_PROMPT

            if not _setting("base_url") or not model:
                logger.error("ai_summary: base_url or model missing from settings.yml")
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            # Read results from cache — populated by post_search() hook
            results = _cache_get(query)
            if not results:
                logger.warning(
                    "ai_summary: no cached results for %r — "
                    "post_search may not have run yet", query
                )
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            logger.info("ai_summary: summarising %d results for %r", len(results), query)

            def generate():
                cached = _db_get(query, "compact")
                if cached:
                    yield "data: \"[CACHED]\"\n\n"
                    yield f"data: {json.dumps(cached)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                chunks: list = []
                try:
                    for chunk in _stream_llm(query, results, model,
                                             max_tokens, system_prompt):
                        chunks.append(chunk)
                        yield f"data: {json.dumps(chunk)}\n\n"
                except Exception as exc:
                    logger.warning("ai_summary stream error: %s", exc)
                if chunks:
                    _db_set(query, "compact", "".join(chunks))
                yield "data: [DONE]\n\n"

            return Response(
                stream_with_context(generate()),
                mimetype="text/event-stream",
                headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
            )

        # ── More panel endpoint ──────────────────────────────────────────
        @app.route("/ai_summary_more", methods=["GET"])
        def ai_summary_more_api():
            query = freq.args.get("q", "").strip()[:_MAX_QUERY_LEN]
            if not query:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            model_more    = _setting("model_more") or _setting("model")
            max_tokens    = int(_setting("max_tokens_more", 800))
            system_prompt =  _DEFAULT_PROMPT_MORE

            if not _setting("base_url") or not model_more:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            results = _cache_get(query)
            if not results:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            def generate():
                cached = _db_get(query, "more")
                if cached:
                    # Send full JSON as a single chunk — JS progressive renderer
                    # handles a one-shot payload identically to a streamed one.
                    yield f"data: {json.dumps(cached)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                chunks: list = []
                try:
                    for chunk in _stream_llm(query, results, model_more,
                                             max_tokens, system_prompt):
                        chunks.append(chunk)
                        yield f"data: {json.dumps(chunk)}\n\n"
                except Exception as exc:
                    logger.warning("ai_summary_more stream error: %s", exc)
                if chunks:
                    _db_set(query, "more", "".join(chunks))
                yield "data: [DONE]\n\n"

            return Response(
                stream_with_context(generate()),
                mimetype="text/event-stream",
                headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
            )

        # ── Script injection ─────────────────────────────────────────────
        @app.after_request
        def inject_ai_script(response):
            if not response.content_type.startswith("text/html"):
                return response
            try:
                body = response.get_data(as_text=True)
                if 'id="results"' not in body and "id='results'" not in body:
                    return response
                # Cache-busting version param — changes every minute so updates
                # are picked up quickly without waiting for the hourly rollover.
                _v = str(int(time.time() // 60))
                script = f'\n<script src="/static/themes/simple/js/ai_summary.js?v={_v}"></script>'
                body = body.replace("</body>", script + "\n</body>")
                response.set_data(body)
            except Exception as exc:
                logger.warning("ai_summary inject error: %s", exc)
            return response

        return True

    # ── post_search: cache results as SearXNG fetches them ────────────────────

    def post_search(
        self,
        request: "SXNG_Request",
        search:  "SearchWithPlugins",
    ) -> list:
        """
        Cache the search results so the GET endpoint can use them
        without any internal HTTP call or bot detection issues.
        The client only ever sends the query string — never result data.
        Category filtering is handled client-side by isGeneralTab() in
        ai_summary.js, which reads the URL param directly.
        """
        if search.search_query.pageno > 1:
            return []

        query = search.search_query.query
        if not query:
            return []

        results = []
        for r in search.result_container.get_ordered_results():
            content = _read(r, "content")
            if content:
                results.append({
                    "title":   _read(r, "title"),
                    "url":     _read(r, "url"),
                    "content": content[:400],
                })

        if results:
            _cache_set(query, results)
            logger.info("ai_summary: cached %d results for %r", len(results), query)

        return []
