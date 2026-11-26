"""Open Library Search API."""

from lib.providers._shadow import API_UA, cache, format_results, get_json

API = "https://openlibrary.org/search.json"
MIRRORS = ("https://openlibrary.org",)
HEADERS = {"User-Agent": API_UA}
FIELDS = "title,author_name,key,first_publish_year,edition_count,language"


def parse_response(payload: dict, limit: int = 20) -> dict:
    documents = payload.get("docs") if isinstance(payload, dict) else None
    if not isinstance(documents, list):
        raise ValueError("Open Library response schema changed")
    results = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        title = " ".join(str(document.get("title") or "").split())
        key = str(document.get("key") or "").strip()
        if not title or not key.startswith("/works/"):
            continue
        authors = document.get("author_name") or []
        results.append(
            {
                "title": title,
                "author": ", ".join(str(author).strip() for author in authors if str(author).strip()),
                "url": f"https://openlibrary.org{key}",
                "year": str(document.get("first_publish_year") or ""),
                "editions": document.get("edition_count"),
                "languages": list(document.get("language") or []),
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict:
    payload = get_json(
        API,
        params={"q": query, "limit": limit, "fields": FIELDS},
        headers=HEADERS,
        mirrors=MIRRORS,
    )
    return parse_response(payload, limit)
