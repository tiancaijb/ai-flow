"""Filter upstream items by a condition.

YAML:
  - name: only_long
    type: filter
    field: title
    contains: AI                    # keep items where title contains "AI"

Other operators (pick one per filter):
  contains: substring match (case-insensitive)
  starts_with: prefix match
  regex: Python regex match
  min_length: keep items where field string length >= N

Output: only items that pass the filter.
"""

import re as _re
from typing import Any, Dict, List


def run(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
    items = ctx.get("_items", [])
    field = cfg.get("field", "")
    out = []

    for item in items:
        val = item.get(field, "")

        if "contains" in cfg:
            if cfg["contains"].lower() in str(val).lower():
                out.append(item)
        elif "starts_with" in cfg:
            if str(val).startswith(cfg["starts_with"]):
                out.append(item)
        elif "regex" in cfg:
            if _re.search(cfg["regex"], str(val)):
                out.append(item)
        elif "min_length" in cfg:
            if len(str(val)) >= cfg["min_length"]:
                out.append(item)
        else:
            out.append(item)  # no filter = pass through

    return out
