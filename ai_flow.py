#!/usr/bin/env python3
"""
ai-flow — A workflow engine designed for AI, not humans.

Design principles:
  - YAML in, results out. No drag-and-drop, no web UI.
  - Few built-in nodes. Each has a clear contract and small parameter surface.
  - Template strings: `{{key}}` (resolved from current item + shared context).
  - LLM calls: one per upstream item (preserves per-item originals).
  - Auto-retry with exponential backoff, configurable per node.
  - Error messages are actionable: AI can read them and fix the YAML.
  - One command = one execution. No daemons, no polling.

Synopsis:
  ai-flow run pipeline.yaml       # execute
  ai-flow dry-run pipeline.yaml   # show plan without calling APIs
  ai-flow validate pipeline.yaml  # schema check only
"""

import csv as csv_mod
import json
import os
import sys
import time
import traceback
from itertools import count
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Tuple, Union

import feedparser
import requests
import yaml


# ═══════════════════════════════════════════════════════════════════════════
# Template engine  (only `{{key.path}}` – no filters, no loops)
# ═══════════════════════════════════════════════════════════════════════════

def template(expr: str, ctx: dict) -> str:
    """Resolve `{{key.subkey}}` expressions in *expr* against *ctx*.
    Special prefix `env.NAME` reads from os.environ."""
    out = []
    i = 0
    while i < len(expr):
        if expr[i:i+2] == "{{":
            j = expr.find("}}", i + 2)
            if j == -1:
                out.append(expr[i:])
                break
            key_path = expr[i+2:j].strip()
            try:
                parts = key_path.split(".")
                val: Any = ctx
                start = 0
                if parts[0] == "env" and len(parts) >= 2:
                    val = os.environ
                    start = 1
                for k in parts[start:]:
                    if isinstance(val, Mapping):
                        val = val[k]
                    elif isinstance(val, list) and k.isdigit():
                        val = val[int(k)]
                    else:
                        raise KeyError(k)
                out.append(str(val))
            except (KeyError, IndexError, TypeError, ValueError):
                out.append(f"{{{{{key_path} (missing)}}}}")
            i = j + 2
        else:
            out.append(expr[i])
            i += 1
    return "".join(out)


# ═══════════════════════════════════════════════════════════════════════════
# Node runners — each is a pure function  (cfg, ctx) → items
# ═══════════════════════════════════════════════════════════════════════════

def node_rss(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
    """Fetch an RSS/Atom feed. Returns one dict per entry."""
    feed = feedparser.parse(cfg["url"])
    return [
        {
            "title": e.get("title", ""),
            "description": e.get("description", ""),
            "summary": e.get("summary", ""),
            "link": e.get("link", ""),
            "published": e.get("published", ""),
            "author": e.get("author", ""),
        }
        for e in feed.entries
    ]


def node_llm(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
    """Call an OpenAI-compatible chat API. *ctx* must contain `prompt`
    (the user message). Every other key in *ctx* is available as template
    context for the prompt template.

    Required cfg keys:
      model        – model name (e.g. "deepseek-chat")
      api_key      – API key string, or "env:VARNAME" to read from env
    Optional:
      base_url     – default "https://api.deepseek.com/v1"
      temperature  – default 0.3
      max_tokens   – default 4096
    """
    model = cfg.get("model", "deepseek-chat")
    base_url = cfg.get("base_url", "https://api.deepseek.com/v1")
    temperature = cfg.get("temperature", 0.3)
    max_tokens = cfg.get("max_tokens", 4096)

    api_key = cfg["api_key"]
    if api_key.startswith("env:"):
        api_key = os.environ.get(api_key[4:], "")

    # Render prompt template against *ctx*
    content = template(cfg.get("prompt", ""), ctx)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    response_text = data["choices"][0]["message"]["content"]

    return [{**ctx, "_output": response_text, "_usage": data.get("usage", {})}]


def node_mapper(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
    """Map each upstream item through a set of field mappings.
    Useful for renaming, extracting, or composing fields.

    Required: none (operates on upstream items)
    """
    # The context contains `_items` (list of upstream item dicts)
    items = ctx.get("_items", [])
    mapping = cfg.get("mapping", {})
    out = []
    for item in items:
        item_ctx = {**item, **ctx}
        mapped = {}
        for dst, src_tpl in mapping.items():
            mapped[dst] = template(src_tpl, item_ctx)
        out.append(mapped)
    return out


def node_csv(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
    """Write upstream items to a CSV file."""
    items = ctx.get("_items", [])
    columns = cfg.get("columns", {})
    path = template(cfg.get("file", "/tmp/ai-flow.csv"), ctx)
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for item in items:
        item_ctx = {**item, **ctx}
        rows.append({col: template(tpl, item_ctx) for col, tpl in columns.items()})

    with open(path, "w", newline="", encoding="utf-8") as f:
        if rows:
            w = csv_mod.DictWriter(f, fieldnames=list(columns.keys()))
            w.writeheader()
            w.writerows(rows)

    return [{"file": path, "rows": len(rows)}]


# ── Registry ────────────────────────────────────────────────────────────────

RUNNERS = {
    "rss": node_rss,
    "llm": node_llm,
    "mapper": node_mapper,
    "csv": node_csv,
}


# ═══════════════════════════════════════════════════════════════════════════
# Engine
# ═══════════════════════════════════════════════════════════════════════════

class PipelineError(Exception):
    """An error in pipeline definition or execution."""
    def __init__(self, node: str, msg: str):
        self.node = node                                    # type: str
        self.msg = msg                                      # type: str


def _run_node(
    name: str,
    ntype: str,
    cfg: dict,
    retry: int,
    upstream_items: List[Dict[str, Any]],
    shared_ctx: dict,
    dry_run: bool,
) -> Tuple[bool, List[Dict[str, Any]], str, int]:
    """Execute one node (with retry). Returns (ok, items, error, attempts)."""
    runner = RUNNERS.get(ntype)

    if dry_run:
        return True, [{"_dry_run": True, "type": ntype, "config": cfg}], "", 0

    if not runner:
        return False, [], f"Unknown node type '{ntype}'. Available: {list(RUNNERS.keys())}", 0

    max_attempts = retry + 1
    last_err = ""

    for attempt in range(1, max_attempts + 1):
        try:
            t0 = time.time()
            ctx = {**shared_ctx, "_items": upstream_items}

            if ntype == "llm":
                # One LLM call per upstream item
                out: List[Dict[str, Any]] = []
                for item in upstream_items:
                    item_ctx = {**ctx, **item}
                    result = runner(cfg=cfg, ctx=item_ctx)
                    out.extend(result)
            else:
                out = runner(cfg=cfg, ctx=ctx)
                if not isinstance(out, list):
                    out = [out]

            return True, out, "", attempt

        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < max_attempts:
                wait = min(2 ** (attempt - 1), 30)
                print(f"  ⚠ {name}: attempt {attempt}/{max_attempts} failed, "
                      f"retry in {wait}s…", file=sys.stderr)
                time.sleep(wait)

    return False, [], f"Failed after {max_attempts} tries. Last error: {last_err}", max_attempts


def execute(pipeline: dict, dry_run: bool = False) -> List[dict]:
    """Execute a complete pipeline. Returns a list of step-result dicts."""
    steps = pipeline.get("pipeline", [])
    results: List[dict] = []
    shared_ctx: Dict[str, Any] = {}
    last_output: List[Dict[str, Any]] = []

    for step in steps:
        name = step.get("name", f"step_{len(results)}")
        ntype = step.get("type", "")
        retry = step.get("retry", 2)
        node_cfg = {k: v for k, v in step.items()
                    if k not in ("name", "type", "retry", "input")}

        ok, items, err, attempts = _run_node(
            name=name, ntype=ntype, cfg=node_cfg,
            retry=retry, upstream_items=last_output,
            shared_ctx=shared_ctx, dry_run=dry_run,
        )

        result = {
            "node": name, "ok": ok,
            "items": items, "error": err,
            "attempts": attempts,
        }
        results.append(result)

        if not ok:
            break
        shared_ctx[name] = {"items": items}
        last_output = items

    return results


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def validate(pipeline: dict) -> List[str]:
    """Return a list of validation errors (empty = valid)."""
    errors: List[str] = []
    steps = pipeline.get("pipeline")
    if not steps:
        errors.append("No 'pipeline' key found, or pipeline is empty.")
        return errors
    for i, step in enumerate(steps):
        name = step.get("name", f"step[{i}]")
        if "type" not in step:
            errors.append(f"{name}: missing 'type'")
        elif step["type"] not in RUNNERS:
            errors.append(f"{name}: unknown type '{step['type']}' — "
                          f"available: {list(RUNNERS.keys())}")
    return errors


def _fmt_error(node: str, err: str) -> str:
    """Format an error so AI can act on it."""
    # Truncate very long error messages
    if len(err) > 500:
        err = err[:500] + "…"
    return f"❌ {node}: {err}"


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__.strip())
        return 1

    cmd = sys.argv[1]
    path = Path(sys.argv[2])

    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 1

    pipeline = yaml.safe_load(path.read_text())

    if cmd == "validate":
        errors = validate(pipeline)
        if errors:
            for e in errors:
                print(f"  ✗ {e}")
            return 1
        print("✅ Pipeline is valid.")
        return 0

    if cmd == "dry-run":
        print(f"🔍 Dry-run: {path}\n")
        results = execute(pipeline, dry_run=True)
        for r in results:
            ok = "✓" if r["ok"] else "✗"
            cfg_preview = r["items"][0].get("config", {}) if r["items"] else {}
            print(f"  {ok} {r['node']}  ({cfg_preview})")
        return 0

    if cmd == "run":
        print(f"▶ {path}\n")
        t0 = time.time()
        results = execute(pipeline, dry_run=False)

        for r in results:
            if r["ok"]:
                n = len(r["items"])
                extra = ""
                if r["attempts"] > 1:
                    extra = f" ({r['attempts']} tries)"
                print(f"  ✅ {r['node']} → {n} item(s){extra}")
            else:
                print(f"  ❌ {r['node']}: {r['error']}")

        elapsed = (time.time() - t0) * 1000
        ok = all(r["ok"] for r in results)
        label = "✅ Success" if ok else "❌ Failed"
        print(f"\n{label}  ({elapsed:.0f}ms)")
        return 0 if ok else 1

    print(f"Unknown command: {cmd}. Use run, validate, or dry-run.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
