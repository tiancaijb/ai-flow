# ai-flow

AI-friendly workflow engine. Define pipelines in YAML with a small set of
well-documented nodes. One command to run. No web UI, no drag-and-drop.

## Why?

Existing workflow tools (n8n, Zapier, etc.) are designed for humans:
visual editors, rich parameter panels, 800+ nodes. When an AI tries to
build workflows on top of them, the debugging loop is painful: guess
parameters → create workflow → run → interpret error → delete → retry.

**ai-flow** is designed from the ground up for AI-driven workflow
generation: YAML in, results out.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Validate pipeline definition
python3 ai_flow.py validate rss_translate.yaml

# Dry-run (show plan without calling APIs)
python3 ai_flow.py dry-run rss_translate.yaml

# Execute
DEEPSEEK_KEY=sk-xxx python3 ai_flow.py run rss_translate.yaml
```

## Pipeline Format

```yaml
pipeline:
  - name: step1
    type: rss
    url: https://example.com/feed.xml

  - name: step2
    type: llm
    retry: 3           # max retries (default 2)
    model: deepseek-chat
    api_key: env:MY_KEY  # read from env var $MY_KEY
    prompt: |           # template: {{field}} from upstream items
      翻译：{{title}}

  - name: step3
    type: csv
    file: ~/output.csv
    columns:
      Title: "{{title}}"
      Translation: "{{_output}}"
```

## Built-in Nodes

| type     | What it does                                              |
|----------|----------------------------------------------------------|
| `rss`    | Fetch & parse RSS/Atom feed                              |
| `llm`    | Call OpenAI-compatible API (one call per upstream item)  |
| `mapper` | Rename, extract, or compose fields                       |
| `csv`    | Write upstream items to a CSV file                       |

## Key Design Choices

- **No configuration GUIs.** All node config is in the YAML.
- **Small node surface.**  Built-in nodes only. Extend via code, not plugins.
- **{{field}} templates.** Simple, predictable — no custom expression language.
- **Per-item LLM.** Each upstream item gets its own LLM call automatically.
- **Auto-retry.** Every node retries with exponential backoff.
- **Actionable errors.** Error messages tell you what to fix, not a stack trace.
