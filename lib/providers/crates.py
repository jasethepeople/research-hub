"""crates tier."""
import lib.providers.http as http

API = "https://crates.io/api/v1/crates"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(API, params={"q": query.strip(), "per_page": min(max(limit, 1), 50)},
        headers={"User-Agent": "research-hub-tier/0.1"},
    timeout=30.0)
    results = []
    for c in response.json().get("crates", []):
        results.append({
            "title": f"{c.get('name')} (crates.io)",
            "author": c.get("id") or "",
            "url": f"https://crates.io/crates/{c.get('id', '')}",
            "snippet": (c.get("description") or "")[:300],
        })
    return {"results": results, "note": ""}

