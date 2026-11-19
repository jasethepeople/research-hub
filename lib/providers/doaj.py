"""doaj tier."""
import urllib.parse

import lib.providers.http as http

API = "https://doaj.org/api/search/articles/"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(f"{API}{urllib.parse.quote(query.strip())}", params={"pageSize": min(max(limit,
    1), 50)}, timeout=30.0)
    items = response.json().get("results", [])
    results = []
    for hit in items:
        doc = hit.get("bibjson", {})
        authors = ", ".join(a.get("name", "") for a in doc.get("author", [])[:3])
        links = doc.get("link", [])
        url = next((link.get("url", "") for link in links if link.get("type") == "fulltext"), "")
        results.append({
            "title": doc.get("title") or "Untitled",
            "author": authors,
            "url": url,
            "snippet": (doc.get("abstract") or "")[:300],
        })
    return {"results": results, "note": ""}

