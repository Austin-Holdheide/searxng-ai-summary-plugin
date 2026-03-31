# SearXNG AI Summary Plugin — Copilot Instructions

## Project Overview

A SearXNG plugin that injects a streaming AI summary above search results using any OpenAI-compatible API (LM Studio, Ollama, OpenAI, Groq, etc.). Deployed entirely via Docker with volume-mounted files — no image rebuilds needed.

## File Layout

```
ai_summary.py          ← SearXNG plugin: Flask routes + result caching + script injection
ai_summary.js          ← Frontend: SSE consumer, typewriter effect, progressive JSON renderer
ai_summary.css         ← Standalone stylesheet (CSS is also inlined in the JS)
ai_summary_box.html    ← HTML template reference
docker-compose.yml     ← Docker setup; all files volume-mounted into the container
searxng/settings.yml   ← All configuration (SearXNG + plugin LLM settings)
```

## Architecture

### Backend (`ai_summary.py`)

- Implements `SXNGPlugin(Plugin)` — a SearXNG plugin class
- **`post_search()` hook** — caches search results in `_cache` (keyed by lowercase query, TTL 5 min, max 500 entries) after SearXNG fetches them
- **`GET /ai_summary`** — streams compact summary tokens via SSE; reads results from in-process cache (client sends query string only — never result data)
- **`GET /ai_summary_more`** — streams structured JSON (overview + sections + follow_up) via SSE for the "More" panel
- **`after_request` hook** — injects `<script src="/static/themes/simple/js/ai_summary.js">` into every HTML response containing `id="results"`

### Frontend (`ai_summary.js`)

- Self-contained IIFE; auto-runs on search result pages
- Compact summary: reads SSE stream, drains a queue with a typewriter animation
- More panel: progressive JSON parser using balanced-brace counting to render sections as they arrive (does not wait for full JSON)

### Security Model

- Client sends the query string only — never result snippets
- `post_search()` populates the cache server-side; GET endpoints read from it
- No internal HTTP calls from endpoints; no bot detection issues
- Query length capped at 500 characters

## Critical Conventions

### Two Settings Blocks (do not merge them)

`PluginCfg` only accepts `active: true/false`. Adding **any other key** under the plugin entry crashes SearXNG:

```
TypeError: PluginCfg.__init__() got an unexpected keyword argument 'base_url'
```

Always keep the config split:

```yaml
# Inside plugins: — ONLY active: allowed
plugins:
  searx.plugins.ai_summary.SXNGPlugin:
    active: true

# Top-level key — all LLM settings go here
ai_summary:
  base_url: "http://127.0.0.1:1234/v1"
  model: "google/gemma-3-1b"
  ...
```

### YAML Indentation

Plugin keys must have **exactly 2-space indentation**. Wrong indentation causes SearXNG to silently ignore or crash on the settings file.

### Models

- Always use `-instruct` or `-it` model variants — base models ignore the system prompt
- The `model_more` endpoint requires a model that reliably returns valid JSON; larger models do this better
- `model` = fast model for compact summary; `model_more` = smarter model for structured deep-dive

## Run & Restart

```powershell
# Start (first time or after docker-compose.yml changes)
docker compose up -d

# Apply changes to settings.yml, ai_summary.py, or ai_summary.js
docker compose restart searxng

# Watch live logs
docker compose logs -f searxng

# Filter for plugin messages
docker compose logs searxng | findstr ai_summary
```

No image rebuild is needed — all source files are volume-mounted.

## Common Pitfalls

| Symptom | Root Cause |
|---------|-----------|
| `PluginCfg unexpected keyword` | LLM settings placed inside `plugins:` block |
| SearXNG won't start | YAML indentation error in settings.yml |
| No summary, plugin silent | `active: true` missing or `ai_summary.py` not volume-mounted |
| More panel shows raw JSON | Old JS cached — hard refresh (`Ctrl+Shift+R`) |
| Summary contains markdown | Base model (not instruct) ignoring system prompt |
| `Connection refused` | LM Studio server not started / wrong IP in `base_url` |

## Key Settings

| Key | Description |
|-----|-------------|
| `base_url` | OpenAI-compatible API root (no trailing slash) |
| `api_key` | API key — any non-empty string for local providers |
| `model` | Fast model for compact summary |
| `model_more` | Smart model for More panel (needs reliable JSON output) |
| `max_results` | Result snippets sent to LLM (default: 5) |
| `max_tokens` | Max tokens for compact summary (default: 300) |
| `max_tokens_more` | Max tokens for More panel (default: 800) |
| `timeout` | Request timeout in seconds (default: 60) |
| `system_prompt` | Override system prompt for compact summary |
| `system_prompt_more` | Override system prompt for More panel — must instruct JSON output |
