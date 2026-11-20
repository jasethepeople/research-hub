"""openverse tier: Creative-Commons image search (api.openverse.org)."""
import html
from typing import Any

import lib.providers.http as http

API = "https://api.openverse.org/v1/images/"


def search(query: str, limit: int = 20) -> dict[str, Any]:
    response = http.get(
        API,
        params={
            "q": query.strip(),
            "page_size": min(max(limit, 1), 20),
            "filter_dead": "false",
        },
        timeout=30.0,
    )
    results = []
    for item in response.json().get("results", []):
        results.append(
            {
                "title": html.unescape(item.get("title") or "Untitled"),
                "author": item.get("creator") or "",
                "url": item.get("foreign_landing_url") or item.get("url") or "",
                "link": item.get("thumbnail") or item.get("url") or "",
                "snippet": f"{item.get('license', '')} · {item.get('source', '')}".strip(),
            }
        )
    return {"results": results, "note": ""}