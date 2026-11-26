"""Crossref scholarly metadata search."""

from lib.providers._shadow import API_UA, cache, format_results, get_json

API = "https://api.crossref.org/works"
MIRRORS = ("https://api.crossref.org",)
HEADERS = {"User-Agent": API_UA}
SELECT = "DOI,title,author,issued,container-title,URL,type"


def parse_response(payload: dict, limit: int = 20) -> dict:
    message = payload.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("items"), list):
        raise ValueError("Crossref response has no message.items list")
    results = []
    for item in message["items"]:
        if not isinstance(item, dict):
            continue
        titles = item.get("title") or []
        doi = str(item.get("DOI") or "").strip()
        title = " ".join(str(titles[0] if titles else "").split())
        url = str(item.get("URL") or (f"https://doi.org/{doi}" if doi else "")).strip()
        if not title or not url:
            continue
        date_parts = (item.get("issued") or {}).get("date-parts") or []
        year = str(date_parts[0][0]) if date_parts and date_parts[0] else ""
        authors = [
            " ".join(
                part
                for part in (str(author.get("given") or "").strip(), str(author.get("family") or "").strip())
                if part
            )
            for author in item.get("author", [])
            if isinstance(author, dict)
        ]
        containers = item.get("container-title") or []
        results.append(
            {
                "title": title,
                "author": ", ".join(name for name in authors if name),
                "url": url,
                "doi": doi,
                "journal": " ".join(str(containers[0] if containers else "").split()),
                "year": year,
                "type": str(item.get("type") or ""),
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict:
    payload = get_json(
        API,
        params={"query.bibliographic": query, "rows": limit, "select": SELECT},
        headers=HEADERS,
        mirrors=MIRRORS,
    )
    return parse_response(payload, limit)
