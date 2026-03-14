"""
SearXNG AI Summary Plugin
=========================
Adds an AI-generated summary box above search results, similar to
Google's AI Overview and DuckDuckGo's Search Assist.

HOW IT WORKS
------------
SearXNG's plugin system works in three stages per search:
  1. pre_search  – runs before engines are queried (we don't use this)
  2. (engines run and collect results)
  3. post_search – runs after all results are collected (this is our hook)

Our post_search() method:
  a. Grabs the top N results already collected by SearXNG
  b. Builds a prompt: query + result snippets
  c. POSTs to your OpenAI-compatible endpoint (/v1/chat/completions)
  d. Returns an Answer() object — SearXNG renders it in the answer box

CONFIGURATION (settings.yml)
-----------------------------
Two blocks are required:

  # 1. Enable the plugin (only `active` is allowed under plugins:)
  plugins:
    searx.plugins.ai_summary.SXNGPlugin:
      active: true

  # 2. LLM settings in a separate top-level key
  ai_summary:
    base_url: "http://192.168.1.238/v1"
    api_key:  "ollama"
    model:    "openai/gpt-oss-20b"
    max_results: 5
    max_tokens:  300
    timeout:     20
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
from searx.result_types import Answer

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Request
    from searx.search import SearchWithPlugins

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "You are a helpful assistant embedded in a search engine. "
    "Given the user's search query and the top results, write a concise "
    "3-5 sentence summary that directly answers the query. "
    "Do NOT open with 'Based on the results'. No markdown."
)


def _setting(key: str, default=None):
    """Read from the top-level ai_summary: block in settings.yml."""
    return get_setting(f"ai_summary.{key}", default)


def _read(result, key: str) -> str:
    """
    Safely read a field from a result object.
    SearXNG results are MainResult objects (attribute access),
    but may also be plain dicts in some cases — handle both.
    """
    try:
        # Try attribute access first (MainResult objects)
        val = getattr(result, key, None)
        if val is not None:
            return str(val)
        # Fall back to dict access
        if hasattr(result, "get"):
            val = result.get(key)
            if val is not None:
                return str(val)
    except Exception:
        pass
    return ""


class SXNGPlugin(Plugin):
    """AI summary box above search results via any OpenAI-compatible API."""

    id = "ai_summary"
    keywords: list = []  # empty = run on every query

    def __init__(self, plg_cfg: "PluginCfg") -> None:
        # IMPORTANT: PluginCfg only accepts `active:`.
        # All LLM settings are read from the separate `ai_summary:` top-level
        # key in settings.yml via get_setting() — NOT from plg_cfg.
        super().__init__(plg_cfg)
        self.info = PluginInfo(
            id=self.id,
            name=_("AI Summary"),
            description=_("Show an AI-generated summary above search results"),
            preference_section="general",
        )

    def _build_prompt(self, query: str, results: list) -> str:
        lines = [f'Search query: "{query}"\n\nTop results:\n']
        for i, r in enumerate(results, 1):
            title   = _read(r, "title")
            url     = _read(r, "url")
            content = _read(r, "content")
            lines.append(f"{i}. {title} ({url})\n   {content}\n")
        lines.append("\nWrite a concise summary answering the query.")
        return "\n".join(lines)

    def _call_llm(self, query: str, results: list) -> t.Optional[str]:
        base_url = _setting("base_url")
        api_key  = _setting("api_key", "no-key")
        model    = _setting("model")
        max_tokens    = int(_setting("max_tokens", 300))
        timeout       = float(_setting("timeout", 20))
        system_prompt = _setting("system_prompt") or _DEFAULT_PROMPT

        if not base_url:
            logger.error("ai_summary: 'ai_summary.base_url' is missing from settings.yml")
            return None
        if not model:
            logger.error("ai_summary: 'ai_summary.model' is missing from settings.yml")
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
                {"role": "user",   "content": self._build_prompt(query, results)},
            ],
        }

        try:
            resp = httpx.post(endpoint, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

        except httpx.TimeoutException:
            logger.warning(
                "ai_summary: timed out after %ss — raise ai_summary.timeout in settings.yml",
                timeout,
            )
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "ai_summary: HTTP %s — check ai_summary.base_url and ai_summary.api_key",
                exc.response.status_code,
            )
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            logger.warning("ai_summary: unexpected response format: %s", exc)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("ai_summary: error calling LLM: %s", exc)

        return None

    def post_search(
        self,
        request: "SXNG_Request",
        search:  "SearchWithPlugins",
    ) -> list:
        # Skip page 2+ — summary only on page 1
        if search.search_query.pageno > 1:
            return []

        # Collect results that have a content snippet
        # Use _read() because results are MainResult objects, not dicts
        text_results = [
            r for r in search.result_container.get_ordered_results()
            if _read(r, "content")
        ]
        if not text_results:
            return []

        max_results = int(_setting("max_results", 5))
        query       = search.search_query.query

        summary = self._call_llm(query, text_results[:max_results])
        if summary:
            # Answer() renders in the highlighted box above search results —
            # same area used by the Calculator and Self-Info built-in plugins.
            return [Answer(answer=summary)]

        return []