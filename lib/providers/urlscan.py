"""urlscan tier: urlscan.io public scan search (pages, infrastructure, campaigns)."""
import lib.providers.http as http

API = "https://urlscan.io/api/v1/search/"


def search(query: str, limit: int = 20) -> dict:
    response = http.get(API, params={"q": query.strip() or "*", "size": str(min(max(limit, 1), 100))}, timeout=45.0)
    results = []
    for hit in response.json().get("results", [])[:limit]:
        page = hit.get("page", {})
        results.append(
            {
                "title": str(page.get("title") or page.get("url") or hit.get("task", {}).get("dom")),
                "author": str(page.get("domain") or ""),
                "url": str(hit.get("result") or f"https://urlscan.io/scan/{hit.get('_id')}"),
                "year": str(hit.get("task", {}).get("time") or "")[:10],
                "link": str(page.get("screenshot") or ""),
                "snippet": str(page.get("url") or ""),
                "tier": "urlscan",
            }
        )
    return {"results": results, "note": "urlscan.io public scans"}
