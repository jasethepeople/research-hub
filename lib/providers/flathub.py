"""flathub tier."""
import httpx

API = "https://flathub.org/api/v2/search"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = httpx.post(API, json={"query": query.strip(), "runtime": "flathub"},
        headers={"User-Agent": "research-hub-tier/0.1", "Flathub-V2-Search-Extra": "true"},
    timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    results = []
    for app in response.json().get("hits", [])[:limit]:
        results.append({
            "title": app.get("name") or app.get("app_id") or "Untitled",
            "author": app.get("developer_name") or "",
            "url": f"https://flathub.org/apps/{app.get('app_id', '')}",
            "snippet": app.get("summary") or "",
        })
    return {"results": results, "note": ""}

