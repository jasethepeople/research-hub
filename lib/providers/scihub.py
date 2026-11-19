"""Sci-Hub tier: shadow library resolver. Keyword search resolves real DOIs via
Crossref, then maps each onto its Sci-Hub mirror page."""

import httpx

from lib.providers.http import get

MIRROR = "https://sci-hub.ru"
CROSSREF = "https://api.crossref.org/works"
SELECT = "DOI,title,author,issued"


def search(query: str, limit: int = 20) -> dict:
    response = get(
        CROSSREF,
        params={
            "query.bibliographic": query.strip(),
            "rows": min(max(limit, 1), 40),
            "select": SELECT,
        },
        timeout=25.0,
        headers={"User-Agent": "ResearchHub scihub-tier/0.1 (mailto:research-hub@users.noreply.github.com)"},
    )
    items = response.json().get("message", {}).get("items", [])
    results = []
    for item in items:
        doi = item.get("DOI", "")
        if not doi:
            continue
        title = " ".join((item.get("title") or [""])[0].split())
        authors = ", ".join(
            f"{author.get('given', '')} {author.get('family', '')}".strip()
            for author in item.get("author", [])
        )
        issued = (item.get("issued", {}).get("date-parts") or [[None]])[0][0]
        results.append(
            {
                "doi": doi,
                "title": title,
                "author": authors,
                "url": f"{MIRROR}/{doi}",
                "year": issued,
            }
        )
    return {"results": results, "note": "open the URL on Sci-Hub to read or download the PDF"}


def probe(doi: str) -> dict:
    """True only when Sci-Hub actually serves the payload for this identifier."""
    doi = (doi or "").strip()
    if not doi:
        return {"doi": doi, "url": "", "available": False, "note": "empty identifier"}
    url = f"{MIRROR}/{doi}"
    try:
        response = get(url, timeout=20.0)
    except httpx.HTTPStatusError as error:
        return {"doi": doi, "url": url, "available": False, "note": f"HTTP {error.response.status_code}"}
    except httpx.HTTPError as error:
        return {"doi": doi, "url": url, "available": False, "note": error.__class__.__name__}
    lowered = response.text.lower()
    if "article not found" in lowered or "статье не найдено" in lowered:
        return {"doi": doi, "url": url, "available": False, "note": "not found"}
    has_payload = "iframe" in lowered or "/pdf/" in lowered or "/downloads/" in lowered or "download" in lowered
    return {"doi": doi, "url": url, "available": has_payload, "note": ""}
