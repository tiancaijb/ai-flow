"""Delay / rate-limit between steps.

YAML:
  - name: pause
    type: delay
    seconds: 3         # wait 3 seconds (useful for rate-limiting)

Does not transform data — upstream items pass through unchanged.

For cron-like scheduling, use system crontab to trigger ai-flow:
  0 * * * * cd ~/projects/ai-flow && python3 ai_flow.py run pipeline.yaml
"""

import time as _time
from typing import Any, Dict, List


def run(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
    seconds = cfg.get("seconds", 1)
    _time.sleep(seconds)
    return ctx.get("_items", [])
