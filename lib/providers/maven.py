"""maven tier."""
import lib.providers.http as http

API = "https://search.maven.org/solrsearch/select"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(API, params={"q": query.strip(), "rows": min(max(limit, 1), 50), "wt": "json"}, timeout=30.0)
    results = []
    for doc in response.json().get("response", {}).get("docs", []):
        results.append({
            "title": f"{doc.get('id')} (maven)",
            "author": doc.get("a") or "",
            "url": f"https://central.sonatype.com/artifact/{doc.get('id', '')}",
            "snippet": f"v{doc.get('latestVersion', '')}",
        })
    return {"results": results, "note": ""}

