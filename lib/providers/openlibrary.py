"""Open Library tier (open)."""

import httpx

FIELDS = "title,author_name,key,first_publish_year,edition_count"


def search(query: str, limit: int = 20) -> dict:
    response = httpx.get(
        "https://openlibrary.org/search.json",
        params={"q": query.strip(), "limit": min(max(limit, 1), 50), "fields": FIELDS},
        timeout=25.0,
    )
    response.raise_for_status()
    results = []
    for item in response.json().get("docs", []):
        results.append(
            {
                "title": item.get("title", ""),
                "author": ", ".join(item.get("author_name") or []),
                "url": f"https://openlibrary.org{item.get('key', '')}",
                "year": item.get("first_publish_year"),
                "editions": item.get("edition_count"),
            }
        )
    return {"results": results, "note": ""}
