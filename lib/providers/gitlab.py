"""GitLab tier: public project search on gitlab.com."""

from typing import Any

from lib.providers.http import get

API = "https://gitlab.com/api/v4/projects"


def search(query: str, limit: int = 20) -> dict[str, Any]:
    response = get(
        API,
        params={
            "search": query.strip(),
            "per_page": min(max(limit, 1), 50),
            "order_by": "last_activity_at",
            "simple": "true",
        },
        timeout=30.0,
    )
    projects = response.json()
    results = []
    for item in projects[: max(limit, 1)]:
        namespace = str((item.get("namespace") or {}).get("name") or "")
        stars = item.get("star_count", 0)
        byline = " · ".join(part for part in (namespace, f"★ {stars}" if stars else "") if part)
        results.append(
            {
                "title": str(item.get("path_with_namespace") or item.get("name") or ""),
                "url": str(item.get("web_url") or ""),
                "author": byline,
                "published": str(item.get("created_at") or "")[:10],
                "source": "GitLab",
                "id": str(item.get("id") or ""),
            }
        )
    return {"results": results, "note": ""}