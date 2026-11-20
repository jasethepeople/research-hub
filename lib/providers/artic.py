"""artic tier: Art Institute of Chicago open-access artworks."""
from typing import Any

import lib.providers.http as http

API = "https://api.artic.edu/api/v1/artworks/search"


def search(query: str, limit: int = 20) -> dict[str, Any]:
    response = http.get(
        API,
        params={
            "q": query.strip(),
            "limit": min(max(limit, 1), 25),
            "fields": "id,title,artist_display,date_display,image_id,thumbnail,is_public_domain,api_link",
        },
        timeout=30.0,
    )
    results = []
    for item in response.json().get("data", []):
        image_id = item.get("image_id") or ""
        link = (
            f"https://www.artic.edu/iiif/2/{image_id}/full/400,/0/default.jpg" if image_id else ""
        )
        results.append(
            {
                "title": item.get("title") or "Untitled",
                "author": (item.get("artist_display") or "").split("\n")[0],
                "url": item.get("api_link") or "",
                "link": link,
                "snippet": item.get("date_display") or "",
            }
        )
    return {"results": results, "note": ""}