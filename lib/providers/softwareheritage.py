"""Software Heritage tier: search the archive of all collected source code origins."""

from typing import Any

from lib.providers.http import get

API = "https://archive.softwareheritage.org/api/1/origin/search"


def search(query: str, limit: int = 20) -> dict[str, Any]:
    response = get(
        f"{API}/{query.strip()}/",
        params={"limit": min(max(limit, 1), 50)},
        headers={"Accept": "application/json"},
        timeout=30.0,
    )
    payload = response.json()
    results = []
    for item in payload.get("results", [])[: max(limit, 1)]:
        url = str(item.get("url") or "")
        if not url:
            continue
        title = url.removeprefix("https://").removeprefix("http://").rstrip("/")
        results.append(
            {
                "title": title[:160],
                "url": url,
                "author": "",
                "published": "",
                "source": "SWH",
                "id": url,
            }
        )
    return {"results": results, "note": ""}