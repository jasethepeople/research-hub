"""GitHub tier: repository search via the public REST API (token optional)."""

import os
from typing import Any

from lib.providers.http import get

API = "https://api.github.com/search/repositories"


def search(query: str, limit: int = 20) -> dict[str, Any]:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = get(
        API,
        params={
            "q": query.strip(),
            "per_page": min(max(limit, 1), 50),
            "sort": "best-match",
        },
        headers=headers,
        timeout=30.0,
    )
    payload = response.json()
    results = []
    for item in payload.get("items", [])[: max(limit, 1)]:
        stars = item.get("stargazers_count", 0)
        language = item.get("language") or ""
        author = str(item.get("owner", {}).get("login") or "")
        byline = " · ".join(part for part in (author, language, f"★ {stars}" if stars else "") if part)
        results.append(
            {
                "title": str(item.get("full_name") or ""),
                "url": str(item.get("html_url") or ""),
                "author": byline,
                "published": str(item.get("created_at") or "")[:10],
                "source": "GitHub",
                "id": str(item.get("full_name") or ""),
            }
        )
    return {"results": results, "note": ""}