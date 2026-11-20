"""loc_maps tier: Library of Congress map collections (rare/historical maps)."""
import lib.providers.http as http

API = "https://www.loc.gov/maps/"


def search(query: str, limit: int = 20) -> dict:
    response = http.get(
        API,
        params={"q": query.strip() or "world", "fo": "json", "c": str(min(max(limit, 1), 50))},
        timeout=45.0,
    )
    items = response.json().get("results", [])
    results = []
    for item in items:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        image = (item.get("image_url") or [None])
        results.append(
            {
                "title": str(item.get("title")),
                "author": str(item.get("creator") or ""),
                "url": str(item.get("id") or item.get("url") or ""),
                "year": str(item.get("date") or ""),
                "link": str(image[0]) if image else "",
                "snippet": str(item.get("description") or "")[:200],
                "tier": "loc_maps",
            }
        )
    return {"results": results, "note": "Library of Congress map collections (scans)"}
