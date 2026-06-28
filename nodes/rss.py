"""RSS/Atom feed fetcher.

YAML:
  - name: fetch
    type: rss
    url: https://hnrss.org/frontpage

Output: list of dicts with title, description, summary, link, published, author.
"""

import feedparser
from typing import Any, Dict, List


def run(cfg: dict, ctx: dict) -> List[Dict[str, Any]]:
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
