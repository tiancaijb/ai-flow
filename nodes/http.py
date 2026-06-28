"""Generic HTTP request.

YAML:
  - name: fetch_api
    type: http
    method: POST                        # optional, default GET
    url: https://api.example.com/data
    headers:                            # optional
      Authorization: "Bearer {{env.TOKEN}}"
    body:                               # optional (JSON)
      query: "{{title}}"

Output: parsed JSON response. If response is a JSON array, each element becomes
an item. If a JSON object, wrapped in a list. If not JSON, returns {text, status}.
"""

import json as _json
from typing import Any, Dict, List

import requests

from ai_flow import template


def run(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
    method = cfg.get("method", "GET").upper()
    url = template(cfg["url"], ctx)

    headers = {}
    for k, v in cfg.get("headers", {}).items():
        headers[k] = template(v, ctx)

    body = cfg.get("body")
    if body and isinstance(body, dict):
        body_str = _json.dumps({k: template(str(v), ctx) for k, v in body.items()})
    elif body:
        body_str = template(str(body), ctx)
    else:
        body_str = None

    resp = requests.request(method, url, headers=headers, data=body_str, timeout=30)
    resp.raise_for_status()

    try:
        data = resp.json()
        return data if isinstance(data, list) else [data]
    except _json.JSONDecodeError:
        return [{"text": resp.text, "status": resp.status_code}]
