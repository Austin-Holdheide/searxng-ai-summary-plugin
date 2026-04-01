# SearXNG AI Summary Plugin

![SearXNG AI Summary Plugin](images/Ai%20Summary.png)

Adds a streaming AI summary above search results using any OpenAI-compatible endpoint — just like Google's AI Overview and DuckDuckGo's Search Assist. Built for self-hosted SearXNG with Docker.

---

## Features

- **Instant results** — search results load at full speed, summary streams in after
- **Typewriter effect** — text appears character by character as the LLM generates it
- **"More" button** — expands into a structured deep-dive powered by a smarter model
- **Progressive rendering** — sections appear as they complete, not all at once
- **Code blocks** — commands render with syntax highlighting and a Copy button
- **Generating indicator** — spinning loader shows while the More panel is still generating
- **Auto-injected** — no template files need editing, ever
- **Dark/light theme** — follows SearXNG's theme automatically
- **Any OpenAI-compatible backend** — LM Studio, Ollama, OpenAI, Groq, and more

---


## How It Works

### The Async Flow

```
User types query
      │
      ▼
SearXNG queries engines ───────────────── Results appear instantly (no wait)
      │
      ▼
Browser loads ai_summary.js             (auto-injected by the plugin)
      │
      ▼
JS creates summary box with blinking cursor above results
      │
      ▼
JS reads result snippets from the page DOM
      │
      ▼
JS opens SSE stream → POST /ai_summary
      │
      ▼
Flask streams tokens from fast model ──── Characters appear one by one
      │
      ▼
Stream ends → "More ▾" button appears
      │
      ▼ (user clicks More)
JS opens SSE stream → POST /ai_summary_more
      │
      ├── overview arrives   → renders paragraph
      ├── section 1 closes   → renders heading + bullets/code blocks
      ├── section 2 closes   → renders heading + bullets/code blocks
      ├── follow_up closes   → renders "Explore More" questions
      └── stream ends        → generating indicator disappears
```

### Why Two Settings Blocks

SearXNG's `PluginCfg` dataclass only accepts `active: true/false`. Putting any
other key under a plugin entry crashes SearXNG on startup:

```
TypeError: PluginCfg.__init__() got an unexpected keyword argument 'base_url'
```

The fix is two separate blocks in `settings.yml`:

```yaml
# Block 1 — inside plugins: (ONLY active: allowed here)
plugins:
  searx.plugins.ai_summary.SXNGPlugin:
    active: true

# Block 2 — new top-level key (all LLM config goes here)
ai_summary:
  base_url: "http://127.0.0.1:1234/v1"
  model: "google/gemma-3-1b"
  model_more: "openai/gpt-oss-20b"
  ...
```

The plugin reads Block 2 via `get_setting("ai_summary.base_url")`.

### How the Script Is Injected

The plugin's `init(app)` method runs once at Flask startup and registers:

1. **`POST /ai_summary`** — streaming SSE endpoint for the compact summary
2. **`POST /ai_summary_more`** — streaming SSE endpoint for the More panel
3. **`after_request` hook** — appends `<script src="ai_summary.js">` to every
   HTML page that contains `id="results"`. No template editing ever needed.

### How Streaming Works

Both endpoints use `stream: true` in the LLM request and return
`text/event-stream` (SSE). The browser reads each chunk using the Fetch
`ReadableStream` API.

**Compact summary** — characters are pushed into a queue and drained at a
speed that matches the LLM: fast when tokens arrive in bursts, slow when
the model pauses. The blinking cursor shows while generation is ongoing.

**More panel** — raw JSON streams in. A progressive parser scans the
incomplete buffer on every chunk using balanced-brace counting and regex
matching to extract completed pieces and render them immediately:
- `"overview": "..."` → paragraph rendered
- Each completed `{...}` in `sections` → section rendered with code blocks
- `"follow_up": [...]` → questions rendered

---

## File Layout

```
searxng-ai-summary/
├── docker-compose.yml     ← start here
├── ai_summary.py          ← plugin: Flask routes + script injection
├── ai_summary.js          ← frontend: streaming loader + progressive renderer
└── searxng/
    └── settings.yml       ← all configuration lives here
```

---

## Setup

### Prerequisites

- Docker Desktop installed and running
- LM Studio (or any OpenAI-compatible API) running on your network
- At least one model loaded and ready

### Step 1 — Get the files

Your folder must look exactly like this:

```
your-folder/
├── docker-compose.yml
├── ai_summary.py
├── ai_summary.js
└── searxng/
    └── settings.yml
```

### Step 2 — Edit `searxng/settings.yml`

**Enable the plugin** — add this inside the `plugins:` section:

```yaml
  searx.plugins.ai_summary.SXNGPlugin:
    active: true
```

**Configure the LLM** — add this as a new top-level key (not inside `plugins:`):

```yaml
ai_summary:
  base_url: "http://127.0.0.1:1234/v1"   # your LM Studio IP:port
  api_key:  "lm-studio"                       # any string for local providers
  model:       "google/gemma-3-1b"            # fast model — compact summary
  model_more:  "openai/gpt-oss-20b"           # smart model — More panel
  max_results: 5
  max_tokens:  300
  max_tokens_more: 800
  timeout: 60
```

**Find your IP address** (Windows):
```powershell
ipconfig
# Look for IPv4 Address under your active network adapter
```

**Find your model name** — open LM Studio → Developer tab → copy the
model identifier shown under "API Model Identifier".

**Set a secret key**:
```yaml
server:
  secret_key: "replace-this-with-something-long-and-random"
```

### Step 3 — Start

```powershell
cd C:\path\to\your-folder
docker compose up -d
```

### Step 4 — Open SearXNG

```
http://localhost:8080
```

Search for anything. Results load immediately. The AI summary types itself
in above the results. Click **More** for the structured deep-dive.

---

## Configuration Reference

All settings live in `searxng/settings.yml` under the `ai_summary:` key.

| Key | Description |
|-----|-------------|
| `base_url` | OpenAI-compatible API root URL (no trailing slash) |
| `api_key` | API key — any non-empty string for local providers |
| `model` | Fast model used for the compact summary |
| `model_more` | Smart model used for the More panel |
| `max_results` | Result snippets sent to the LLM (default: 5) |
| `max_tokens` | Max tokens for compact summary (default: 300) |
| `max_tokens_more` | Max tokens for More panel (default: 800) |
| `timeout` | Request timeout in seconds (default: 60) |
| `system_prompt` | System prompt for compact summary |
| `system_prompt_more` | System prompt for More panel — must instruct the model to return JSON |

### Supported Backends

| Provider | `base_url` | `api_key` |
|----------|-----------|-----------|
| LM Studio | `http://YOUR_IP:1234/v1` | `lm-studio` |
| Ollama | `http://YOUR_IP:11434/v1` | `ollama` |
| OpenAI | `https://api.openai.com/v1` | `sk-...` |
| Groq | `https://api.groq.com/openai/v1` | `gsk_...` |
| Together AI | `https://api.together.xyz/v1` | your key |
| vLLM | `http://YOUR_IP:8000/v1` | any string |

### Recommended Models

| Model | Speed | Quality | Best for |
|-------|-------|---------|----------|
| `google/gemma-3-1b-it` | ⚡⚡⚡⚡ | ★★★ | `model` — fastest compact summary |
| `google/gemma-3-4b-it` | ⚡⚡⚡ | ★★★★ | `model` — best speed/quality balance |
| `microsoft/phi-4-mini-instruct` | ⚡⚡⚡ | ★★★★ | `model` — great instruction following |
| `qwen/qwen2.5-7b-instruct` | ⚡⚡ | ★★★★★ | `model_more` — best structured output |
| `mistralai/mistral-7b-instruct` | ⚡⚡ | ★★★★ | `model_more` — reliable JSON output |
| `openai/gpt-oss-20b` | ⚡ | ★★★★★ | `model_more` — highest quality |

Always use `-it` or `-instruct` variants. The More panel requires a model
that reliably returns valid JSON — larger models do this better.

---

## After Any Change

```powershell
docker compose restart searxng
```

Changes to `settings.yml`, `ai_summary.py`, or `ai_summary.js` all take
effect after a restart. No rebuild needed — all files are volume-mounted.

---

## Troubleshooting

```powershell
# Watch live logs
docker compose logs -f searxng

# Filter for plugin messages only
docker compose logs searxng | findstr ai_summary
```

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PluginCfg unexpected keyword` | LLM settings inside `plugins:` block | Move them to the separate `ai_summary:` top-level block |
| SearXNG won't start | YAML indentation error | Check that all plugin keys have exactly 2 spaces indent |
| `Connection refused` | LM Studio server not started | Open LM Studio → Developer → flip Status toggle to ON |
| No summary, no error | Plugin not loaded | Check `active: true` is set and `ai_summary.py` is volume-mounted |
| Summary never appears | LLM timeout | Increase `timeout` or use a smaller model |
| More panel shows raw JSON | Old JS file cached | Hard refresh (`Ctrl+Shift+R`) or restart container |
| More panel errors | Smart model too slow | Increase `timeout`, reduce `max_tokens_more`, or use a faster model |
| HTTP 401/403 | Wrong API key | Fix `api_key` in settings.yml |
| HTTP 404 | Wrong URL or model name | Fix `base_url` or `model` / `model_more` |
| Summary has markdown | Model ignoring system prompt | Switch to an `-instruct` or `-it` model variant |

### Test your LLM directly

```powershell
@'
{
  "model": "YOUR_MODEL_NAME",
  "max_tokens": 150,
  "stream": false,
  "messages": [
    {"role": "system", "content": "Summarize in 2 sentences. No markdown."},
    {"role": "user",   "content": "What is Apache web server?"}
  ]
}
'@ | Out-File -FilePath test.json -Encoding utf8

curl.exe -X POST http://YOUR_IP:1234/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d "@test.json"
```

A working response has `choices[0].message.content` with plain text. If this
works but the plugin doesn't, check the Docker logs for the exact error.

---

## License

MIT