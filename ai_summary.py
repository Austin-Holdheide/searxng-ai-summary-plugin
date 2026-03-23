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
    "You are a helpful assistant in a search engine. "
    "Write a concise 3-5 sentence summary answering the query. "
    "No markdown. No 'Based on the results.'"
)

_DEFAULT_PROMPT_MORE = (
    "You are a helpful assistant in a search engine. "
    "Return ONLY valid JSON — no markdown fences, no explanation. "
    'Shape: {"overview":"paragraph","sections":[{"title":"Title","items":['
    '{"type":"text","value":"bullet"},{"type":"code","lang":"bash","value":"cmd"}'
    ']}],"follow_up":["Q1?","Q2?","Q3?"]} '
    "Use type=code for commands with correct lang. type=text for plain bullets. "
    "2-4 sections, 2-5 items. Exactly 3 follow_up questions."
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


def _cache_set(query: str, results: list):
    key = query.lower().strip()
    with _cache_lock:
        _cache[key] = {"results": results, "ts": time.time()}
        # Evict entries older than TTL
        now = time.time()
        expired = [k for k, v in _cache.items() if now - v["ts"] > _CACHE_TTL]
        for k in expired:
            del _cache[k]


def _cache_get(query: str) -> list:
    key = query.lower().strip()
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry["ts"] < _CACHE_TTL:
            return entry["results"]
    return []


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
        from flask import request as freq, Response, stream_with_context

        # ── Compact summary endpoint ─────────────────────────────────────
        @app.route("/ai_summary", methods=["GET"])
        def ai_summary_api():
            query = freq.args.get("q", "").strip()
            if not query:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            model         = _setting("model")
            max_tokens    = int(_setting("max_tokens", 300))
            system_prompt = _setting("system_prompt") or _DEFAULT_PROMPT

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
                try:
                    for chunk in _stream_llm(query, results, model,
                                             max_tokens, system_prompt):
                        yield f"data: {json.dumps(chunk)}\n\n"
                except Exception as exc:
                    logger.warning("ai_summary stream error: %s", exc)
                yield "data: [DONE]\n\n"

            return Response(
                stream_with_context(generate()),
                mimetype="text/event-stream",
                headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
            )

        # ── More panel endpoint ──────────────────────────────────────────
        @app.route("/ai_summary_more", methods=["GET"])
        def ai_summary_more_api():
            query = freq.args.get("q", "").strip()
            if not query:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            model_more    = _setting("model_more") or _setting("model")
            max_tokens    = int(_setting("max_tokens_more", 800))
            system_prompt = _setting("system_prompt_more") or _DEFAULT_PROMPT_MORE

            if not _setting("base_url") or not model_more:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            results = _cache_get(query)
            if not results:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            def generate():
                try:
                    for chunk in _stream_llm(query, results, model_more,
                                             max_tokens, system_prompt):
                        yield f"data: {json.dumps(chunk)}\n\n"
                except Exception as exc:
                    logger.warning("ai_summary_more stream error: %s", exc)
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
                # Cache-busting version param forces browser to reload JS
                import time as _time
                _v = str(int(_time.time() // 3600))  # changes every hour
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
