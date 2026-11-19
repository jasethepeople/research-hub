"""rubygems tier."""
import lib.providers.http as http

API = "https://rubygems.org/api/v1/search.json"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(API, params={"query": query.strip(), "page": 1}, timeout=30.0)
    results = []
    for g in response.json():
        results.append({
            "title": f"{g.get('name')} (rubygems)",
            "author": g.get("authors") or "",
            "url": g.get("project_uri") or g.get("homepage_uri") or "",
            "snippet": (g.get("info") or "")[:300],
        })
    return {"results": results[:limit], "note": ""}

