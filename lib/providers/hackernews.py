"""hackernews tier."""
import lib.providers.http as http

API = "https://hn.algolia.com/api/v1/search"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(API, params={"query": query.strip(), "hitsPerPage": min(max(limit, 1), 50)}, timeout=30.0)
    results = []
    for hit in response.json().get("hits", []):
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        results.append({
            "title": hit.get("title") or hit.get("story_title") or "HN item",
            "author": hit.get("author") or "",
            "url": url,
            "snippet": (hit.get("story_text") or hit.get("comment_text") or "")[:300],
        })
    return {"results": results, "note": ""}

