"""openalex tier."""
import lib.providers.http as http

API = "https://api.openalex.org/works"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(API, params={"search": query.strip(), "per-page": min(max(limit, 1), 50),
        "mailto": "hub@example.org"},
    timeout=30.0)
    works = response.json().get("results", [])
    results = []
    for w in works:
        authors = ", ".join(a["author"]["display_name"] for a in (w.get("authorships") or [])[:3])
        results.append({
            "title": w.get("title") or w.get("display_name") or "Untitled",
            "author": authors,
            "url": (w.get("primary_location") or {}).get("landing_page_url") or w.get("doi") or "",
            "snippet": (w.get("abstract_inverted_index") and "OpenAlex work") or "",
        })
    return {"results": results, "note": ""}

