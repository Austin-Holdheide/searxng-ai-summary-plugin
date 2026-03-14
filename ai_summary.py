"""
SearXNG AI Summary Plugin — Async Edition
==========================================
Shows an AI summary box that loads AFTER search results appear,
so users see results instantly with no long wait.

HOW IT WORKS (async flow)
--------------------------
1. User searches → SearXNG returns results immediately (fast)
2. init(app) has registered two things on Flask startup:
   a. POST /ai_summary  — an API endpoint that calls your LLM
   b. after_request hook — injects <script> tag into results page HTML
3. Browser loads results page + our JS
4. JS reads result snippets already on the page
5. JS POSTs to /ai_summary with query + snippets
6. LLM responds → JS injects a styled summary box above results

WHY TWO SEPARATE THINGS IN settings.yml
-----------------------------------------
SearXNG's PluginCfg dataclass ONLY accepts `active: true/false`.
Any other key causes a crash. So LLM config lives in a top-level
`ai_summary:` block and is read via get_setting().

settings.yml structure:
  plugins:
    searx.plugins.ai_summary.SXNGPlugin:
      active: true          # ← only this is allowed here

  ai_summary:               # ← all LLM settings go here
    base_url: "http://192.168.1.238:1234/v1"
    api_key:  "lm-studio"
    model:    "openai/gpt-oss-20b"
    max_results: 5
    max_tokens:  300
    timeout:     30
    system_prompt: >
      You are a helpful assistant in a search engine ...
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
    "You are a helpful assistant embedded in a search engine. "
    "Given the user's search query and the top search results, write a "
    "concise 3-5 sentence summary that directly answers the query. "
    "Do NOT open with 'Based on the results' or similar phrases. "
    "Do NOT use markdown. Plain sentences only."
)


def _setting(key: str, default=None):
    """Read from the top-level ai_summary: block in settings.yml."""
    return get_setting(f"ai_summary.{key}", default)


def _read(result, key: str) -> str:
    """Read a field from either a MainResult object or a plain dict."""
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


class SXNGPlugin(Plugin):
    """Async AI summary box — results load first, summary loads after."""

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

    # ------------------------------------------------------------------
    # Flask setup — runs once at startup
    # ------------------------------------------------------------------

    def init(self, app) -> bool:
        """
        Register two things on the Flask app:
          1. POST /ai_summary  — API endpoint that calls the LLM
          2. after_request     — injects <script> tag into results pages
                                 (no template changes needed!)
        """
        from flask import request as flask_request, jsonify, Response

        # ── 1. API endpoint ──────────────────────────────────────────────
        @app.route("/ai_summary", methods=["POST"])
        def ai_summary_api():
            data    = flask_request.get_json(silent=True) or {}
            query   = data.get("query", "").strip()
            results = data.get("results", [])

            if not query or not results:
                return jsonify({"summary": ""})

            base_url = _setting("base_url")
            model    = _setting("model")

            if not base_url or not model:
                logger.error(
                    "ai_summary: base_url or model missing from settings.yml"
                )
                return jsonify({"summary": "", "error": "misconfigured"})

            summary = _call_llm(query, results)
            return jsonify({"summary": summary or ""})

        # ── 2. Script injection ──────────────────────────────────────────
        @app.after_request
        def inject_ai_script(response):
            """
            Inject our JS into every HTML results page automatically.
            This means we never need to edit results.html.
            """
            if not response.content_type.startswith("text/html"):
                return response
            try:
                body = response.get_data(as_text=True)
                # Only inject on pages that have search results
                if 'id="results"' not in body and "id='results'" not in body:
                    return response
                script = (
                    '\n<script src="/static/themes/simple/js/ai_summary.js">'
                    "</script>"
                )
                body = body.replace("</body>", script + "\n</body>")
                response.set_data(body)
            except Exception as exc:
                logger.warning("ai_summary: could not inject script: %s", exc)
            return response

        return True  # plugin is active

    # ------------------------------------------------------------------
    # post_search — not used in async mode, kept for compatibility
    # ------------------------------------------------------------------

    def post_search(
        self,
        request: "SXNG_Request",
        search: "SearchWithPlugins",
    ) -> list:
        return []


# ------------------------------------------------------------------
# LLM call — used by the Flask endpoint above
# ------------------------------------------------------------------

def _build_prompt(query: str, results: list) -> str:
    lines = [f'Search query: "{query}"\n\nTop results:\n']
    for i, r in enumerate(results, 1):
        # results from the JS are plain dicts {title, url, content}
        title   = r.get("title", "") if isinstance(r, dict) else _read(r, "title")
        url     = r.get("url", "")   if isinstance(r, dict) else _read(r, "url")
        content = r.get("content", "") if isinstance(r, dict) else _read(r, "content")
        lines.append(f"{i}. {title} ({url})\n   {content}\n")
    lines.append("\nWrite a concise 3-5 sentence summary answering the query.")
    return "\n".join(lines)


def _call_llm(query: str, results: list) -> t.Optional[str]:
    base_url      = _setting("base_url")
    api_key       = _setting("api_key", "no-key")
    model         = _setting("model")
    max_tokens    = int(_setting("max_tokens", 300))
    timeout       = float(_setting("timeout", 30))
    system_prompt = _setting("system_prompt") or _DEFAULT_PROMPT
    max_results   = int(_setting("max_results", 5))

    if not base_url or not model:
        return None

    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers  = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model":       model,
        "max_tokens":  max_tokens,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": _build_prompt(query, results[:max_results])},
        ],
    }

    try:
        resp = httpx.post(endpoint, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except httpx.TimeoutException:
        logger.warning(
            "ai_summary: timed out (%ss) — increase ai_summary.timeout in settings.yml",
            timeout,
        )
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "ai_summary: HTTP %s — check ai_summary.base_url / api_key in settings.yml",
            exc.response.status_code,
        )
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.warning("ai_summary: unexpected LLM response format: %s", exc)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("ai_summary: error: %s", exc)

    return None