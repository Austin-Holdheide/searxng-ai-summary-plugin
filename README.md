# SearXNG AI Summary Plugin

Adds an **AI-generated summary box** above search results — just like Google's
*AI Overview* and DuckDuckGo's *Search Assist* — by querying any
OpenAI-compatible endpoint (local or cloud).

```
┌─────────────────────────────────────────────────────┐
│  ✦  AI Summary                          llama3       │
│                                                      │
│  Python is a high-level, interpreted programming     │
│  language known for its readable syntax and broad    │
│  standard library. It supports multiple paradigms    │
│  including OOP and functional programming …          │
│                                                      │
│  AI-generated · May contain inaccuracies             │
└─────────────────────────────────────────────────────┘

  1. python.org — Welcome to Python.org …
  2. Wikipedia — Python (programming language) …
```

---

## Supported Backends

| Provider | base_url | api_key |
|---|---|---|
| **Ollama** (local) | `http://localhost:11434/v1` | any string |
| **LM Studio** (local) | `http://localhost:1234/v1` | any string |
| **LocalAI** | `http://localhost:8080/v1` | any string |
| **vLLM** | `http://localhost:8000/v1` | any string |
| **OpenAI** | `https://api.openai.com/v1` | `sk-…` |
| **Groq** | `https://api.groq.com/openai/v1` | `gsk_…` |
| **Together AI** | `https://api.together.xyz/v1` | your key |

---

## File Layout

```
searxng-ai-summary/
├── searx/
│   ├── plugins/
│   │   └── ai_summary.py                      ← main plugin
│   ├── templates/
│   │   └── simple/
│   │       └── macros/
│   │           └── ai_summary_box.html        ← Jinja2 macro
│   └── static/
│       └── themes/
│           └── simple/
│               └── css/
│                   └── ai_summary.css         ← styles
├── settings.example.yml                       ← config snippet
├── TEMPLATE_PATCH.html                        ← where to edit results.html
└── README.md
```

---

## Installation

### 1. Copy the plugin

```bash
cp searx/plugins/ai_summary.py  <searxng-root>/searx/plugins/
```

### 2. Copy the template macro

```bash
cp searx/templates/simple/macros/ai_summary_box.html \
   <searxng-root>/searx/templates/simple/macros/
```

### 3. Copy the CSS

```bash
cp searx/static/themes/simple/css/ai_summary.css \
   <searxng-root>/searx/static/themes/simple/css/
```

### 4. Edit `settings.yml`

Add the block from `settings.example.yml` to your SearXNG `settings.yml`,
then add `'AI Summary'` to `enabled_plugins`.

Minimal snippet:

```yaml
plugins:
  ai_summary:
    base_url: "http://localhost:11434/v1"   # change for your backend
    api_key:  "ollama"
    model:    "llama3"

enabled_plugins:
  - ...existing entries...
  - 'AI Summary'
```

### 5. Patch `results.html`

Open `<searxng-root>/searx/templates/simple/results.html`.

**Add the import** near the top (with the other `{% from %}` lines):
```jinja
{% from 'macros/ai_summary_box.html' import ai_summary_box %}
```

**Add the render call** just before the `{% if answers %}` block:
```jinja
{{ ai_summary_box(answers) }}
```

### 6. Link the CSS

In `<searxng-root>/searx/templates/simple/base.html`, inside `<head>`:
```html
<link rel="stylesheet"
      href="{{ url_for('static', filename='themes/simple/css/ai_summary.css') }}">
```

### 7. Install the `httpx` dependency

SearXNG already ships with `httpx` in most installations.  If not:

```bash
pip install httpx
```

### 8. Restart SearXNG

```bash
# systemd
sudo systemctl restart searxng

# Docker
docker compose restart searxng
```

---

## Configuration Reference

| Key | Default | Description |
|---|---|---|
| `base_url` | `http://localhost:11434/v1` | OpenAI-compat API root |
| `api_key` | `ollama` | Bearer token / API key |
| `model` | `llama3` | Model name |
| `max_results` | `5` | Results fed to the LLM |
| `max_tokens` | `300` | Max summary length |
| `timeout` | `20` | HTTP timeout (seconds) |
| `system_prompt` | (see file) | Full LLM system prompt |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No summary appears | Plugin not enabled | Check `enabled_plugins` in settings.yml |
| No summary appears | LLM unreachable | Check `base_url` and that the service is running |
| Timeout errors | Slow local model | Increase `timeout`, use a smaller model |
| Wrong answers | Low-quality model | Use a larger/better model |
| Summary on page 2+ | By design | Plugin only runs on page 1 |

---

## How It Works

1. **`post_search` hook** fires after all search engines return results.
2. The plugin grabs the top `max_results` text results.
3. It builds a prompt containing the query + result snippets.
4. It calls your LLM endpoint via `POST /v1/chat/completions`.
5. The summary is stored in `result_container.answers["ai_summary"]`.
6. The Jinja2 macro reads that key and renders the styled box.

---

## License

MIT
