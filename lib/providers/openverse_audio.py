"""openverse_audio tier: Creative Commons audio (music, tracks, sounds)."""
import lib.providers.http as http

API = "https://api.openverse.org/v1/audio/"


def search(query: str, limit: int = 20) -> dict:
    if not query.strip():
        raise ValueError("search must not be blank")
    response = http.get(
        API,
        params={"q": query.strip(), "page_size": min(max(limit, 1), 50)},
        timeout=30.0,
    )
    results = []
    for item in response.json().get("results", []):
        results.append(
            {
                "title": item.get("title") or "",
                "author": item.get("creator") or item.get("source") or "",
                "url": item.get("foreign_landing_url") or item.get("url") or "",
                "link": item.get("url") or "",
                "snippet": (item.get("license") or "").upper(),
            }
        )
    return {"results": results, "note": ""}
