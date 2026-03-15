"""
SearXNG AI Summary Plugin — Async + Streaming Edition
======================================================
Compact summary and "More" panel both stream token-by-token,
so text appears as it is generated rather than waiting for completion.

ENDPOINTS
----------
  POST /ai_summary        — compact summary (plain text, streamed)
  POST /ai_summary_more   — expanded panel (JSON, streamed then parsed)

CONFIGURATION (settings.yml)
------------------------------
  plugins:
    searx.plugins.ai_summary.SXNGPlugin:
      active: true

  ai_summary:
    base_url:        "http://127.0.0.1:1234/v1"
    api_key:         "lm-studio"
    model:           "google/gemma-3-1b"       # fast model for compact summary
    model_more:      "openai/gpt-oss-20b"      # smart model for More panel
    max_results:     5
    max_tokens:      300
    max_tokens_more: 800
    timeout:         60
    system_prompt: >
      Write a concise 3-5 sentence summary. No markdown. No "Based on the results."
    system_prompt_more: >
      Return ONLY valid JSON. No markdown fences. No explanation.
      Shape: {"overview":"paragraph","sections":[{"title":"Title","items":[
      {"type":"text","value":"bullet"},{"type":"code","lang":"bash","value":"command"}
      ]}],"follow_up":["Q1?","Q2?","Q3?"]}
      Use type=code for commands/code with the correct lang.
      Use type=text for plain bullets. 2-4 sections, 2-5 items each.
"""

import json
import logging
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
    """
    Generator that yields text chunks from the LLM using streaming.
    Yields strings. Raises on connection error.
    """
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
    """Streaming AI summary box with expandable More panel."""

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

        # ── Compact summary — streaming plain text ───────────────────────
        @app.route("/ai_summary", methods=["POST"])
        def ai_summary_api():
            data    = freq.get_json(silent=True) or {}
            query   = data.get("query", "").strip()
            results = data.get("results", [])

            if not query or not results:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            model         = _setting("model")
            max_tokens    = int(_setting("max_tokens", 300))
            system_prompt = _setting("system_prompt") or _DEFAULT_PROMPT

            if not _setting("base_url") or not model:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

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

        # ── More panel — streaming JSON ──────────────────────────────────
        @app.route("/ai_summary_more", methods=["POST"])
        def ai_summary_more_api():
            data    = freq.get_json(silent=True) or {}
            query   = data.get("query", "").strip()
            results = data.get("results", [])

            if not query or not results:
                return Response("data: [DONE]\n\n", mimetype="text/event-stream")

            model_more    = _setting("model_more") or _setting("model")
            max_tokens    = int(_setting("max_tokens_more", 800))
            system_prompt = _setting("system_prompt_more") or _DEFAULT_PROMPT_MORE

            if not _setting("base_url") or not model_more:
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
                script = '\n<script src="/static/themes/simple/js/ai_summary.js"></script>'
                body = body.replace("</body>", script + "\n</body>")
                response.set_data(body)
            except Exception as exc:
                logger.warning("ai_summary inject error: %s", exc)
            return response

        return True

    def post_search(self, request, search) -> list:
        return []