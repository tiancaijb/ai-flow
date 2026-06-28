#!/usr/bin/env python3
"""
ai-flow — A workflow engine designed for AI, not humans.

Design principles:
  - YAML in, results out. No drag-and-drop, no web UI.
  - Plugin-based nodes: add one .py file to nodes/ → auto-registered.
  - Template strings: `{{key}}` (resolved from current item + shared context).
  - LLM calls: one per upstream item (preserves per-item originals).
  - Auto-retry with exponential backoff, configurable per node.
  - Error messages are actionable: AI can read them and fix the YAML.
  - One command = one execution. No daemons, no polling.

Synopsis:
  ai-flow run pipeline.yaml       # execute
  ai-flow dry-run pipeline.yaml   # show plan without calling APIs
  ai-flow validate pipeline.yaml  # schema check
  ai-flow nodes                   # list available nodes
"""

import importlib
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
# Plugin loader: auto-discover nodes from nodes/*.py
# ═══════════════════════════════════════════════════════════════════════════

def _load_nodes() -> Dict[str, Any]:
    """Import every nodes/*.py and return {name: run_function}."""
    nodes_dir = Path(__file__).resolve().parent / "nodes"
    runners: Dict[str, Any] = {}
    if not nodes_dir.is_dir():
        return runners
    for f in sorted(nodes_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        mod_name = f"nodes.{f.stem}"
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "run"):
                desc = (mod.__doc__ or "").strip().split("\n")[0]
                runners[f.stem] = mod.run
        except Exception as e:
            print(f"  ⚠ Failed to load node '{f.stem}': {e}", file=sys.stderr)
    return runners


RUNNERS = _load_nodes()


# ═══════════════════════════════════════════════════════════════════════════
# Engine
# ═══════════════════════════════════════════════════════════════════════════

def _run_node(
    name: str,
    ntype: str,
    cfg: dict,
    retry: int,
    upstream_items: List[dict],
    shared_ctx: dict,
    dry_run: bool,
) -> Tuple[bool, List[dict], str, int]:
    """Execute one node (with retry). Returns (ok, items, error, attempts)."""
    runner = RUNNERS.get(ntype)

    if dry_run:
        return True, [{"_dry_run": True, "type": ntype, "config": cfg}], "", 0

    if not runner:
        return False, [], (
            f"Unknown node type '{ntype}'. Available: {list(RUNNERS.keys())}. "
            f"Add a {ntype}.py to the nodes/ directory with a run(cfg, ctx) function."
        ), 0

    max_attempts = retry + 1
    last_err = ""
    bulk_nodes = {"llm"}  # nodes that need per-item dispatch

    for attempt in range(1, max_attempts + 1):
        try:
            ctx = {**shared_ctx, "_items": upstream_items}

            if ntype in bulk_nodes:
                # One call per upstream item
                out: List[dict] = []
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
    last_output: List[dict] = []

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

        result = {"node": name, "ok": ok, "items": items,
                  "error": err, "attempts": attempts}
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
            errors.append(
                f"{name}: unknown type '{step['type']}'. "
                f"Available: {list(RUNNERS.keys())}"
            )
    return errors


def _describe_node(name: str) -> str:
    """Return the first paragraph of a node's docstring."""
    mod = importlib.import_module(f"nodes.{name}")
    doc = (mod.__doc__ or "No description.").strip()
    # Take everything up to the first blank line or YAML: block
    lines = []
    for line in doc.split("\n"):
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines).strip()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 0

    cmd = sys.argv[1]

    if cmd == "nodes":
        print("Available nodes:\n")
        for name in sorted(RUNNERS):
            print(f"  {name:<12} {_describe_node(name)}")
        return 0

    if len(sys.argv) < 3:
        print(__doc__.strip())
        return 1

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

    print(f"Unknown command: {cmd}. Use run, validate, dry-run, or nodes.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
