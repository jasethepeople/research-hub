"""europemc tier."""
import lib.providers.http as http

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(API, params={"query": query.strip(), "pageSize": min(max(limit, 1), 50), "format": "json"},
    timeout=30.0)
    items = response.json().get("resultList", {}).get("result", [])
    results = []
    for doc in items:
        url = f"https://europepmc.org/article/{doc.get('source', 'MED')}/{doc.get('id', '')}" if doc.get("id") else "https://europepmc.org"
        results.append({
            "title": doc.get("title") or "Untitled",
            "author": doc.get("authorString") or "",
            "url": url,
            "snippet": (doc.get("abstractText") or "")[:300],
        })
    return {"results": results, "note": ""}

