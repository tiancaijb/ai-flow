"""Write upstream items to a CSV file.

YAML:
  - name: save
    type: csv
    file: "{{env.HOME}}/output.csv"
    columns:
      Title: "{{Original}}"
      Translation: "{{Translation}}"

Output: list with one dict: {file, rows}.
"""

import csv as csv_mod
from pathlib import Path
from typing import Any, Dict, List

from ai_flow import template


def run(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
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
