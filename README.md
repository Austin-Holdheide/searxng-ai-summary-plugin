# SearXNG AI Summary Plugin

Adds an AI-generated summary box above search results — like Google's AI Overview
and DuckDuckGo's Search Assist — using any OpenAI-compatible endpoint.

---

## File layout

```
searxng-ai-summary/
├── docker-compose.yml       ← start here
├── ai_summary.py            ← the plugin
└── searxng/
    └── settings.yml         ← all config lives here
```

---

## Quick start

**1. Edit `searxng/settings.yml`**

Change these three lines to match your LLM:

```yaml
ai_summary:
  base_url: "http://192.168.1.238/v1"   # your endpoint
  api_key:  "ollama"                     # your key
  model:    "openai/gpt-oss-20b"         # your model
```

Also set a real secret key:
```yaml
server:
  secret_key: "replace-this-with-something-random"
```

**2. Start**

```bash
sudo docker compose up -d
```

**3. Open** `http://localhost:8080` and search for anything.

---

## How it works

```
User types query
       │
       ▼
SearXNG queries search engines
       │
       ▼
post_search() hook fires  ◄── our plugin runs here
       │
       ├─ takes top 5 result snippets
       ├─ builds a prompt: query + snippets
       ├─ POSTs to /v1/chat/completions
       └─ returns Answer(answer=summary)
                │
                ▼
       SearXNG renders it in the
       answer box above results
```

The plugin uses `get_setting("ai_summary.<key>")` to read config from the
`ai_summary:` top-level block in settings.yml. This is necessary because
SearXNG's `PluginCfg` dataclass only accepts `active: true/false` — putting
any other key under a plugin entry crashes SearXNG on startup.

---

## Supported LLM backends

| Provider     | base_url                              | api_key       |
|--------------|---------------------------------------|---------------|
| Ollama       | `http://localhost:11434/v1`           | any string    |
| LM Studio    | `http://localhost:1234/v1`            | any string    |
| OpenAI       | `https://api.openai.com/v1`           | `sk-...`      |
| Groq         | `https://api.groq.com/openai/v1`      | `gsk_...`     |
| Together AI  | `https://api.together.xyz/v1`         | your key      |
| vLLM         | `http://localhost:8000/v1`            | any string    |

---

## Troubleshooting

```bash
# Watch logs in real time
sudo docker compose logs -f searxng

# Check for plugin errors specifically
sudo docker compose logs searxng | grep -i "ai_summary\|error"
```

| Problem | Fix |
|---|---|
| `PluginCfg unexpected keyword` | You put LLM settings under `plugins:` — move them to `ai_summary:` |
| No summary, no errors | Check `active: true` is set and the plugin file is mounted |
| Timeout errors | Increase `ai_summary.timeout` or use a faster model |
| HTTP 401/403 | Fix `ai_summary.api_key` |
| HTTP 404 | Fix `ai_summary.base_url` or `ai_summary.model` |