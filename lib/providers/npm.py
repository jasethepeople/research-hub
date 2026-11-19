"""npm tier: registry search for JavaScript packages."""

from typing import Any

from lib.providers.http import get

API = "https://registry.npmjs.org/-/v1/search"


def search(query: str, limit: int = 20) -> dict[str, Any]:
    response = get(API, params={"text": query.strip(), "size": min(max(limit, 1), 50)}, timeout=25.0)
    payload = response.json()
    results = []
    for obj in payload.get("objects", [])[: max(limit, 1)]:
        package = obj.get("package", {})
        name = str(package.get("name") or "")
        if not name:
            continue
        links = package.get("links", {})
        publisher = str((package.get("publisher") or {}).get("username") or "")
        version = str(package.get("version") or "")
        byline = " · ".join(part for part in (publisher, f"v{version}" if version else "") if part)
        results.append(
            {
                "title": name,
                "url": str(links.get("npm") or f"https://www.npmjs.com/package/{name}"),
                "author": byline,
                "published": str(package.get("date") or "")[:10],
                "source": "npm",
                "id": name,
            }
        )
    return {"results": results, "note": ""}