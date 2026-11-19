"""dockerhub tier."""
import lib.providers.http as http

API = "https://hub.docker.com/v2/search/repositories"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(API, params={"query": query.strip(), "page_size": min(max(limit, 1), 50)}, timeout=30.0)
    results = []
    for r in response.json().get("results", []):
        results.append({
            "title": f"{r.get('repo_name')} (docker)",
            "author": r.get("repo_owner") or "",
            "url": f"https://hub.docker.com/r/{r.get('repo_name', '')}",
            "snippet": (r.get("short_description") or "")[:300],
        })
    return {"results": results, "note": ""}

