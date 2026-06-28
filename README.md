# ai-flow

> A workflow engine designed for AI, not humans.

Most workflow engines (n8n, Zapier, Temporal) are built for humans: drag-and-drop
editors, rich parameter panels, 800+ integrations. They're great for people. But
when an AI agent tries to build a workflow on top of them, the debugging loop is
painful: guess parameters → create workflow → run → decode error → delete → retry.

**ai-flow** does only what's needed: define your pipeline in YAML, run one command.
No web UI. No drag-and-drop. No undocumented node quirks.

## Install

```bash
git clone https://github.com/tiancaijb/ai-flow.git
cd ai-flow
pip install -r requirements.txt
```

## Quick Start

```yaml
# pipeline.yaml
pipeline:
  - name: fetch_feed
    type: rss
    url: https://hnrss.org/frontpage

  - name: translate
    type: llm
    retry: 4
    model: deepseek-chat
    api_key: "env:DEEPSEEK_KEY"
    prompt: "Translate to Chinese: {{title}}"
    temperature: 0.3

  - name: save
    type: csv
    file: "{{env.HOME}}/translated.csv"
    columns:
      Original: "{{title}}"
      Translation: "{{_output}}"
```

```bash
DEEPSEEK_KEY=sk-xxx python3 ai_flow.py run pipeline.yaml
```

```
▶ pipeline.yaml

  ✅ fetch_feed → 20 item(s)
  ✅ translate → 20 item(s)
  ✅ save → 1 item(s)

✅ Success  (17s)
```

## Built-in Nodes

| Node    | What it does |
|---------|-------------|
| `rss`   | Fetch & parse RSS/Atom feed |
| `llm`   | Call OpenAI-compatible API (one call per upstream item) |
| `mapper`| Rename, extract, or compose fields |
| `csv`   | Write upstream items to a CSV file |

## Commands

```bash
python3 ai_flow.py run pipeline.yaml       # execute
python3 ai_flow.py dry-run pipeline.yaml   # preview without API calls
python3 ai_flow.py validate pipeline.yaml  # schema check
```

## Template Syntax

`{{key.path}}` resolves against the current item context. Special prefixes:

```yaml
{{title}}          # upstream item field
{{env.HOME}}       # environment variable
{{_output}}        # LLM response text (from llm node)
{{_usage}}         # token usage stats (from llm node)
```

## Why Not n8n / Temporal / Prefect?

These tools are excellent — for humans. But AI agents writing workflows need a
different contract:

|                  | n8n | ai-flow |
|------------------|-----|---------|
| UX target        | Person with mouse | AI with text editor |
| Nodes            | 800+ | 4 (small, documented) |
| Build cycle      | Create → UI edit → test → delete | Edit YAML → run |
| Error messages   | `"The 'prompt' parameter is empty"` | `HTTPError 401 at translate` |
| Expression syntax| `={{ }}` + `{{ }}` two systems | One: `{{key}}` |

## Design

ai-flow is intentionally minimal:

- **No server, no daemon.** One Python process per run.
- **Auto-retry.** Every node retries with exponential backoff (configurable).
- **Per-item LLM.** Each upstream item gets its own LLM call automatically.
- **DAG execution.** Each node passes output to the next. No manual wiring.
- **Small surface.** 4 node types cover 80% of AI → LLM → storage pipelines.

## License

MIT
