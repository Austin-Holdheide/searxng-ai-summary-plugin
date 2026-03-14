# SearXNG AI Summary Plugin

Adds an AI-generated summary box above search results using any OpenAI-compatible
endpoint (LM Studio, Ollama, OpenAI, Groq, etc.) — just like Google's AI Overview
and DuckDuckGo's Search Assist.

```
┌─────────────────────────────────────────────────────────────────┐
│  ✦  AI Summary                                                  │
│                                                                 │
│  Minecraft house tutorials are available across multiple        │
│  platforms. Rock Paper Shotgun offers 50 house designs using    │
│  white wool, wood, and stone bricks. Build It provides          │
│  step-by-step guides for survival houses and redstone farms.    │
│                                                                 │
│  AI-generated · May contain inaccuracies · Verify important...  │
└─────────────────────────────────────────────────────────────────┘

  1. rockpapershotgun.com › Minecraft house ideas: 50 best...
  2. builditapp.com › Build It – Minecraft Building Made Simple
  3. ...
```

---

## How It Works

The plugin uses a fully **async architecture** — search results appear immediately
with zero delay, and the AI summary loads after in the background.

```
User types query
       │
       ▼
SearXNG queries search engines ──────────────── results appear instantly
       │
       │  (meanwhile, in the background...)
       │
       ▼
Browser loads ai_summary.js  (injected automatically by the plugin)
       │
       ▼
JS creates "Generating summary…" spinner above results
       │
       ▼
JS reads result snippets already rendered on the page
       │
       ▼
JS POSTs to /ai_summary  (a Flask endpoint registered by the plugin)
       │
       ▼
Flask calls your LLM at base_url/chat/completions
       │
       ▼
LLM returns summary  (5–20 seconds depending on model/hardware)
       │
       ▼
Spinner replaced with styled summary box  ✦ smooth fade-in
```

### Why It's Split Into Two Settings Blocks

SearXNG's plugin configuration system uses a dataclass called `PluginCfg` that
**only accepts `active: true/false`**. If you put any other key (like `base_url`
or `model`) under a plugin entry, SearXNG crashes on startup with:

```
TypeError: PluginCfg.__init__() got an unexpected keyword argument 'base_url'
```

The solution is two separate blocks in `settings.yml`:

```yaml
# Block 1 — under plugins: (ONLY active: allowed here)
plugins:
  searx.plugins.ai_summary.SXNGPlugin:
    active: true

# Block 2 — top-level key (all LLM config goes here)
ai_summary:
  base_url: "http://192.168.1.238:1234/v1"
  model: "google/gemma-3-4b-it"
  ...
```

The plugin reads Block 2 via `get_setting("ai_summary.base_url")` — a SearXNG
built-in that walks the settings dict by dot-separated path.

### How the Script Injection Works

The plugin's `init(app)` method is called once at Flask startup and registers:

1. **`POST /ai_summary`** — a new Flask route that receives the query + result
   snippets from the browser, calls your LLM, and returns the summary as JSON.

2. **`after_request` hook** — intercepts every HTML response. If the page
   contains `id="results"`, it appends a `<script>` tag before `</body>`. This
   means **no template files need to be edited** — ever.

---

## File Layout

```
searxng-ai-summary/
├── docker-compose.yml        ← orchestrates the container
├── ai_summary.py             ← the plugin (Flask routes + post_search hook)
├── ai_summary.js             ← async frontend loader (injected automatically)
└── searxng/
    └── settings.yml          ← all configuration lives here
```

---

## Setup

### Prerequisites

- Docker installed and running
- LM Studio (or any OpenAI-compatible API) running and accessible
- A model loaded in LM Studio

### Step 1 — Clone or download the files

Make sure your folder looks exactly like this:

```
your-folder/
├── docker-compose.yml
├── ai_summary.py
├── ai_summary.js
├── ai_summary.css
├── ai_summary_box.html
└── searxng/
    └── settings.yml
```

### Step 2 — Edit `searxng/settings.yml`

Find the `ai_summary:` block near the bottom and change these three values:

```yaml
ai_summary:
  base_url: "http://192.168.1.238:1234/v1"   # ← your LM Studio IP and port
  api_key:  "lm-studio"                       # ← any string for local providers
  model:    "google/gemma-3-4b-it"            # ← exact model name from LM Studio
```

To find your IP address on Windows:
```powershell
ipconfig
# Look for "IPv4 Address" under your network adapter
```

To find the exact model name: open LM Studio → Developer tab → copy the model
identifier shown at the top.

Also change the secret key to something random:
```yaml
server:
  secret_key: "replace-this-with-something-random-and-long"
```

### Step 3 — Start

```powershell
cd path\to\your-folder
docker compose up -d
```

### Step 4 — Open SearXNG

```
http://localhost:8080
```

Search for anything. The results appear immediately. After a few seconds the
AI summary box fades in above the results.

---

## Configuration Reference

All settings live in `searxng/settings.yml` under the `ai_summary:` key.

| Key | Default | Description |
|-----|---------|-------------|
| `base_url` | — | OpenAI-compatible API URL (no trailing slash) |
| `api_key` | `"lm-studio"` | API key — any string for local providers |
| `model` | — | Exact model identifier |
| `max_results` | `5` | How many result snippets to send to the LLM |
| `max_tokens` | `300` | Max length of the generated summary |
| `timeout` | `30` | Seconds before the LLM request gives up |
| `system_prompt` | (built-in) | Instructions sent to the LLM |

### Supported Backends

| Provider | `base_url` | `api_key` |
|----------|-----------|-----------|
| LM Studio (local) | `http://YOUR_IP:1234/v1` | `lm-studio` |
| Ollama (local) | `http://YOUR_IP:11434/v1` | `ollama` |
| OpenAI | `https://api.openai.com/v1` | `sk-...` |
| Groq | `https://api.groq.com/openai/v1` | `gsk_...` |
| Together AI | `https://api.together.xyz/v1` | your key |

### Recommended Models

| Model | Speed | Quality | Notes |
|-------|-------|---------|-------|
| `google/gemma-3-4b-it` | ⚡⚡⚡ | ★★★★ | Best all-rounder for summaries |
| `microsoft/phi-4-mini-instruct` | ⚡⚡⚡ | ★★★★ | Very fast, great instruction following |
| `qwen/qwen2.5-7b-instruct` | ⚡⚡ | ★★★★★ | Best quality at medium speed |
| `mistralai/mistral-7b-instruct` | ⚡⚡ | ★★★★ | Reliable, follows prompts well |
| `google/gemma-3-1b-it` | ⚡⚡⚡⚡ | ★★★ | Fastest option, decent quality |

Always use `-it` or `-instruct` variants — they follow the system prompt reliably.

---

## After Changing Settings

Any change to `settings.yml` requires a restart:

```powershell
docker compose restart searxng
```

Any change to `ai_summary.py` or `ai_summary.js` also requires a restart
(the files are volume-mounted so no rebuild needed).

---

## Troubleshooting

```powershell
# Watch live logs
docker compose logs -f searxng

# Check for plugin-specific errors
docker compose logs searxng | findstr ai_summary
```

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PluginCfg unexpected keyword` | LLM settings under `plugins:` | Move them to `ai_summary:` top-level block |
| `Connection refused` | Wrong IP/port or LM Studio not running | Check `base_url` and that LM Studio is on |
| No summary, no error | Plugin not active | Confirm `active: true` and `ai_summary.py` is mounted |
| Spinner never goes away | LLM timeout | Increase `timeout`, try a smaller/faster model |
| HTTP 401/403 | Wrong API key | Fix `api_key` |
| HTTP 404 | Wrong URL or model name | Fix `base_url` or `model` |
| Summary has markdown | Model ignoring system prompt | Use an `-instruct` model variant |

### Test your LLM connection directly

```powershell
# Save test payload
@'
{
  "model": "YOUR_MODEL_NAME",
  "max_tokens": 100,
  "messages": [
    {"role": "system", "content": "Summarize in 2 sentences. No markdown."},
    {"role": "user", "content": "What is Python?"}
  ]
}
'@ | Out-File -FilePath test.json -Encoding utf8

# Send it
curl.exe -X POST http://YOUR_IP:1234/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d "@test.json"
```

A working response contains `choices[0].message.content` with a plain text summary.

---

## License

MIT