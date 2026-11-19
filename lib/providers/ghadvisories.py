"""GitHub Security Advisory tier (GHSA). Uses the authenticated REST advisory search."""
import os
from typing import Any

import httpx

API = "https://api.github.com/search/code"

def _token() -> str:
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""

def search(query: str, limit: int = 20) -> dict[str, Any]:
    token = _token()
    if not token:
        return {"results": [], "note": "needs GH_TOKEN for GitHub code search (advisory database)"}
    response = httpx.get(
        API,
        params={"q": f"{query.strip()} repo:github/advisory-database", "per_page": min(max(limit, 1), 50)},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "research-hub-tier/0.1",
        },
        timeout=30.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    results: list[dict[str, Any]] = []
    for item in response.json().get("items", [])[:limit]:
        results.append({
            "title": (item.get("path") or "").rsplit("/", 1)[-1].replace(".json", "") or "advisory",
            "author": "github/advisory-database",
            "url": item.get("html_url") or (
                "https://github.com/github/advisory-database/blob/main/" + str(item.get("path", ""))
            ),
            "snippet": item.get("path") or "",
        })
    return {"results": results, "note": ""}
