"""wikipedia tier."""
import lib.providers.http as http

API = "https://en.wikipedia.org/w/api.php"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(API, params={"action": "query", "list": "search", "srsearch": query.strip(),
        "srlimit": min(max(limit,
    1), 50), "format": "json"}, timeout=30.0, polite=True)
    results = []
    for hit in response.json().get("query", {}).get("search", []):
        import html
        results.append({
            "title": html.unescape(hit.get("title") or ""),
            "author": "",
            "url": "https://en.wikipedia.org/wiki/" + hit.get("title", "").replace(" ", "_"),
            "snippet": html.unescape(hit.get("snippet") or "").replace("<span class=\"searchmatch\">", "").replace(
                "</span>", ""),
        })
    return {"results": results, "note": ""}

