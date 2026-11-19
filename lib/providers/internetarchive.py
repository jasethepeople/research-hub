"""Internet Archive tier: open-library search over the advancedsearch Solr API."""

IA_SEARCH = "https://archive.org/advancedsearch.php"


def _clean(value) -> str:
    return " ".join(str(value).split()) if value else ""


def search(query: str, limit: int = 20) -> dict:
    from lib.providers.http import get

    params = {"q": query, "rows": str(min(max(limit, 1), 50)), "page": "1", "output": "json"}
    pairs = [("fl[]", name) for name in ("identifier", "title", "creator", "year", "mediatype")]
    response = get(IA_SEARCH, params=params, pairs=pairs, timeout=25.0)
    try:
        docs = response.json().get("response", {}).get("docs", [])
    except ValueError:
        return {"results": [], "note": "Internet Archive returned non-JSON output."}
    results = []
    for doc in docs:
        identifier = _clean(doc.get("identifier"))
        if not identifier:
            continue
        creators = doc.get("creator")
        if isinstance(creators, list):
            author = ", ".join(_clean(c) for c in creators[:3])
        else:
            author = _clean(creators)
        results.append(
            {
                "title": _clean(doc.get("title")) or identifier,
                "author": author,
                "url": f"https://archive.org/details/{identifier}",
                "year": _clean(doc.get("year")),
                "mediatype": _clean(doc.get("mediatype")),
            }
        )
    return {"results": results, "note": ""}
