"""LLM caller — one API call per upstream item.

YAML:
  - name: translate
    type: llm
    model: deepseek-chat
    api_key: "env:DEEPSEEK_KEY"      # or plain string
    prompt: "Translate: {{title}}"
    base_url: https://api.deepseek.com/v1   # optional
    temperature: 0.3                         # optional, default 0.3
    max_tokens: 4096                         # optional, default 4096

Output: upstream item fields + _output (LLM response) + _usage (tokens).
"""

import os
from typing import Any, Dict, List

import requests

from ai_flow import template


def run(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
    model = cfg.get("model", "deepseek-chat")
    base_url = cfg.get("base_url", "https://api.deepseek.com/v1")
    temperature = cfg.get("temperature", 0.3)
    max_tokens = cfg.get("max_tokens", 4096)

    api_key = cfg["api_key"]
    if api_key.startswith("env:"):
        api_key = os.environ.get(api_key[4:], "")

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
    resp = requests.post(
        f"{base_url}/chat/completions", json=payload, headers=headers, timeout=180
    )
    resp.raise_for_status()
    data = resp.json()
    response_text = data["choices"][0]["message"]["content"]

    return [{**ctx, "_output": response_text, "_usage": data.get("usage", {})}]
