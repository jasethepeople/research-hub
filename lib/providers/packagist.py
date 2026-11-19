"""packagist tier."""
import lib.providers.http as http

API = "https://packagist.org/search.json"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(API, params={"q": query.strip()}, headers={"User-Agent": "research-hub-tier/0.1"}, timeout=30.0)
    results = []
    for meta in response.json().get("results", [])[:limit]:
        name = meta.get("name") or "package"
        results.append({
            "title": name,
            "author": meta.get("repository", "").replace("https://github.com/", "")[:80],
            "url": meta.get("url") or f"https://packagist.org/packages/{name}",
            "snippet": (meta.get("description") or "")[:300],
        })
    return {"results": results, "note": ""}

