---
name: ai-flow
description: Build and run data pipelines using ai-flow, the workflow engine designed for AI. Use when the user wants to chain RSS → LLM → CSV, batch-translate content, summarize feeds, or build linear data pipelines. Use ai-flow when the task is a multi-step data flow that's too complex for a one-off script but not worth setting up n8n. Preference order: script (simplest) → ai-flow (pipeline) → n8n (most complex).
---

# ai-flow

An AI-friendly workflow engine. Define pipelines in YAML with 4 built-in nodes,
run with one command. No web UI. No drag-and-drop. No 800+ nodes.

**Project:** `~/projects/ai-flow/`
**Engine:** `~/projects/ai-flow/ai_flow.py`
**GitHub:** https://github.com/tiancaijb/ai-flow

## When to use ai-flow vs alternatives

| Scenario | Use | Why |
|----------|-----|-----|
| One-off fetch + transform + save | **Script** | Fastest. No YAML overhead. |
| Multi-step data pipeline you'll reuse | **ai-flow** | YAML is self-documenting. One command to re-run. |
| Complex multi-system orchestration (Slack, DB, webhooks, auth) | **n8n** | 800+ nodes. |
| LLM + RSS + CSV (our canonical demo) | **ai-flow** | Perfect fit: linear, reusable, LLM-heavy. |

## How to execute

```bash
cd ~/projects/ai-flow
python3 ai_flow.py validate pipeline.yaml   # check schema
python3 ai_flow.py dry-run pipeline.yaml    # preview
DEEPSEEK_KEY=sk-xxx python3 ai_flow.py run pipeline.yaml
```

Always validate first, then dry-run, then run. If the user only wants to check a YAML, stop at validate.

**DeepSeek API key** for this machine:
The key is stored encrypted in n8n. To extract it:

```bash
python3 << 'PYEOF'
import json, sqlite3, os, base64, hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

config_path = os.path.expanduser('~/.n8n/config')
with open(config_path) as f:
    key = json.load(f)['encryptionKey'].encode()

conn = sqlite3.connect(os.path.expanduser('~/.n8n/database.sqlite'))
cursor = conn.execute("SELECT data FROM credentials_entity WHERE id = 'Nd2UxgWMPIfZk5q3'")
enc = base64.b64decode(cursor.fetchone()[0])
conn.close()

salt, ct = enc[8:16], enc[16:]
dk = b''
while len(dk) < 48:
    dk += hashlib.md5(dk[-16:] + key + salt if dk else key + salt).digest()
cipher = Cipher(algorithms.AES(dk[:32]), modes.CBC(dk[32:48]))
decryptor = cipher.decryptor()
plain = decryptor.update(ct) + decryptor.finalize()
plain = plain[:-plain[-1]]
print(json.loads(plain)['apiKey'])
PYEOF
```

Use this key as `env:DEEPSEEK_KEY` in YAML (reads from `$DEEPSEEK_KEY` env var).

## Pipeline YAML Format

```yaml
pipeline:
  - name: step_name          # required: unique name
    type: node_type          # required: rss | llm | mapper | csv
    retry: 3                 # optional: max retries (default 2)
    # ... node-specific parameters below ...
```

Data flows linearly from top to bottom. Each node receives the previous
node's output as a list of items. Nodes process items and pass them forward.

## Node Reference

### `rss` — Fetch RSS/Atom Feed

| Parameter | Required | Description |
|-----------|----------|-------------|
| `url` | Yes | Feed URL |

Output: One dict per entry, with fields: `title`, `description`, `summary`,
`link`, `published`, `author`.

```yaml
- name: fetch
  type: rss
  url: https://hnrss.org/frontpage
```

### `llm` — Call LLM API

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `model` | Yes | — | Model name (e.g. `deepseek-chat`) |
| `api_key` | Yes | — | API key, or `env:VARNAME` to read from env |
| `prompt` | Yes | — | User message template with `{{field}}` expressions |
| `base_url` | No | `https://api.deepseek.com/v1` | API base URL |
| `temperature` | No | `0.3` | LLM temperature |
| `max_tokens` | No | `4096` | Max output tokens |

**One LLM call per upstream item automatically.** Each upstream RSS entry
gets its own translation call. Fields from the upstream item are available
in templates.

Output: Each item's original fields + `_output` (LLM response text) +
`_usage` (token usage dict).

```yaml
- name: translate
  type: llm
  retry: 4
  model: deepseek-chat
  api_key: "env:DEEPSEEK_KEY"
  prompt: |
    Translate to Chinese: {{title}}
    {{description}}
  temperature: 0.3
```

### `mapper` — Rename/Extract Fields

| Parameter | Required | Description |
|-----------|----------|-------------|
| `mapping` | Yes | Dict of `destination: "{{source_template}}"` |

Transforms each upstream item into a new dict with the given mapping.

```yaml
- name: extract
  type: mapper
  mapping:
    Original: "{{title}}"
    Link: "{{link}}"
    Translation: "{{_output}}"
```

### `csv` — Write to CSV File

| Parameter | Required | Description |
|-----------|----------|-------------|
| `file` | Yes | Output file path (supports `{{env.HOME}}`) |
| `columns` | Yes | Dict of `column_name: "{{template}}"` |

Each upstream item becomes a CSV row. Columns map templates to CSV columns.

```yaml
- name: save
  type: csv
  file: "{{env.HOME}}/output.csv"
  columns:
    Title: "{{Original}}"
    Link: "{{Link}}"
    Translation: "{{Translation}}"
```

## Template Syntax

| Expression | Resolves to |
|------------|------------|
| `{{title}}` | Item field `title` |
| `{{_output}}` | LLM response text (from `llm` node) |
| `{{_usage}}` | Token usage stats (from `llm` node) |
| `{{env.HOME}}` | Environment variable `$HOME` |
| `{{key.missing}}` | `{{key.missing (missing)}}` (soft-fail, not error) |

## Best Practices

1. **Validate first.** `ai_flow.py validate pipeline.yaml` before anything.
2. **Use `retry` on `llm` nodes.** Network failures happen. 3–5 retries is sane.
3. **Add a `mapper` node after `llm`.** LLM output is noisy; map to clean fields.
4. **Keep `temperature` low for translation tasks** (0.1–0.3).
5. **Never put secrets in YAML.** Use `env:VARNAME` and set env vars at runtime.

## Example: HN RSS → DeepSeek Translation → CSV

See `~/projects/ai-flow/rss_translate.yaml` for the working demo.

Run: `DEEPSEEK_KEY=sk-xxx python3 ai_flow.py run rss_translate.yaml`

## Plugin Architecture

Nodes are auto-discovered from `nodes/*.py`. To add a new node type:

1. Create `nodes/new_node.py` with a `run(cfg, ctx) -> list[dict]` function
2. Add a docstring — the first line becomes the node description in `ai-flow nodes`
3. That's it — no engine changes needed

This is the key advantage vs n8n: AI can write a new node in 20 lines of Python
instead of guessing 50 undocumented parameters on a GUI panel.

Run `python3 ai_flow.py nodes` to see all available nodes with descriptions.

### `http` — Generic HTTP Request

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | Yes | — | Request URL (supports `{{}}` templates) |
| `method` | No | `GET` | HTTP method |
| `headers` | No | `{}` | Dict of header → value |
| `body` | No | — | Request body (dict = JSON; string = raw) |

### `filter` — Filter Items

| Pick ONE | Effect |
|----------|--------|
| `contains` | Keep items where `field` contains substring |
| `starts_with` | Keep items where `field` starts with prefix |
| `regex` | Keep items matching Python regex |
| `min_length` | Keep items where field length >= N |

All filters require a `field` parameter specifying which field to check.

### `delay` — Rate Limiter

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `seconds` | No | `1` | Pause for N seconds |

## Plugin Architecture

Nodes are auto-discovered from `nodes/*.py`. To add a new node type:

1. Create `nodes/new_node.py` with a `run(cfg, ctx) -> list[dict]` function
2. Add a docstring — the first line becomes the node description in `ai-flow nodes`
3. That's it — no engine changes needed

This is the key advantage vs n8n: AI can write a new node in 20 lines of Python
instead of guessing 50 undocumented parameters on a GUI panel.

Run `python3 ai_flow.py nodes` to see all available nodes with descriptions.

## Known Limitations

- Linear pipelines only (no branching/loops).
- No scheduling daemon — trigger via cron or manual `run`.
- Single-machine execution (no distributed workers).
