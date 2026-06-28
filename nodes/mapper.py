"""Map upstream items through field templates.

YAML:
  - name: extract
    type: mapper
    mapping:
      Title: "{{title}}"
      Link: "{{link}}"
      Translation: "{{_output}}"

Output: one dict per upstream item, with only the mapped fields.
"""

from typing import Any, Dict, List

from ai_flow import template


def run(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
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
