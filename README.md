# ai-flow

> A workflow engine designed for AI, not humans.

Most workflow engines (n8n, Zapier, Temporal) are built for humans: drag-and-drop
editors, rich parameter panels, 800+ integrations. They're great for people. But
when an AI agent tries to build a workflow on top of them, the debugging loop is
painful: guess parameters → create workflow → run → decode error → delete → retry.

**ai-flow** does one thing: define your pipeline in YAML, run one command. That's the
whole interface. No UI to navigate, no parameters to guess, no hidden quirks.

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

```bash
$ python3 ai_flow.py nodes
  csv          Write upstream items to a CSV file.
  delay        Delay / rate-limit between steps.
  filter       Filter upstream items by a condition.
  http         Generic HTTP request.
  llm          LLM caller — one API call per upstream item.
  mapper       Map upstream items through field templates.
  rss          RSS/Atom feed fetcher.
```

Add new nodes by dropping a `.py` file in `nodes/` — auto-registered.
Each node is ~30 lines, fully documented, no obscure parameters.

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
| Nodes            | 800+ | 7 (small, documented, extensible) |
| Build cycle      | Create → UI edit → test → delete | Edit YAML → run |
| Error messages   | `"The 'prompt' parameter is empty"` | `HTTPError 401 at translate` |
| Expression syntax| `={{ }}` + `{{ }}` two systems | One: `{{key}}` |

## Adding Nodes (Plugin System)

Create `nodes/my_node.py`:

```python
"""What this node does — shown in `ai-flow nodes`."""

def run(cfg: dict, ctx: dict) -> list[dict]:
    # cfg = YAML parameters for this node
    # ctx = shared context + _items (upstream data)
    return [{"result": "..."}]
```

That's it. No engine changes, no registration. Reload and it's live.

## Design

ai-flow is intentionally minimal:

- **No server, no daemon.** One Python process per run.
- **Plugin-based nodes.** One `.py` file = one node type.
- **Auto-retry.** Every node retries with exponential backoff (configurable).
- **Per-item LLM.** Each upstream item gets its own LLM call automatically.
- **Linear DAG.** Each node passes output to the next. No manual wiring.
- **AI-first.** Small surface, clear contracts, actionable errors.

## AI Agent Integration

ai-flow ships with an **agent skill** — a reference document that teaches your
AI coding agent how to use ai-flow to build and run pipelines on your behalf.
No need to write YAML by hand.

Install it in your agent's skills directory (`ai-flow-skill/SKILL.md`), then tell
your agent: *"翻译 HN 上今天的 AI 新闻，存成 CSV"* — it reads the skill,
writes the pipeline YAML, and runs it.

## License

MIT
