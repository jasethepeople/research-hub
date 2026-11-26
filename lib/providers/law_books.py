"""Search legal history and public-domain law books in Internet Archive."""

from lib.providers._shadow import API_UA, cache, format_results, get_json

API = "https://archive.org/advancedsearch.php"
MIRRORS = ("https://archive.org",)
HEADERS = {"User-Agent": API_UA}


def parse_response(payload: dict, limit: int = 20) -> dict:
    response = payload.get("response")
    if not isinstance(response, dict) or not isinstance(response.get("docs"), list):
        raise ValueError("Internet Archive response has no response.docs list")
    results = []
    for doc in response["docs"]:
        if not isinstance(doc, dict):
            continue
        ident = str(doc.get("identifier") or "").strip()
        title = " ".join(str(doc.get("title") or "").split())
        if not ident or not title:
            continue
        creator = doc.get("creator") or []
        if isinstance(creator, str):
            creators = creator
        else:
            creators = ", ".join(str(name).strip() for name in creator if str(name).strip())
        results.append(
            {
                "title": title,
                "author": creators,
                "url": f"https://archive.org/details/{ident}",
                "identifier": ident,
                "year": str(doc.get("year") or ""),
                "snippet": " ".join(str(doc.get("description") or "").split())[:500],
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict:
    payload = get_json(
        API,
        params={
            "q": f'mediatype:texts AND ({query})',
            "fl[]": ["identifier", "title", "creator", "year", "description"],
            "rows": limit,
            "output": "json",
        },
        headers=HEADERS,
        mirrors=MIRRORS,
    )
    return parse_response(payload, limit)
