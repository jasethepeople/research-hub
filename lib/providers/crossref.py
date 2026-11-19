"""Crossref tier (open): scholarly works metadata."""

from lib.providers.http import get

CROSSREF = "https://api.crossref.org/works"
SELECT = "DOI,title,author,issued,container-title,URL"
POLITE_UA = "ResearchHub crossref-tier/0.1 (mailto:research-hub@users.noreply.github.com)"


def search(query: str, limit: int = 20) -> dict:
    response = get(
        CROSSREF,
        params={
            "query.bibliographic": query.strip(),
            "rows": min(max(limit, 1), 40),
            "select": SELECT,
        },
        timeout=25.0,
        headers={"User-Agent": POLITE_UA},
    )
    items = response.json().get("message", {}).get("items", [])
    results = []
    for item in items:
        issued = (item.get("issued", {}).get("date-parts") or [[None]])[0][0]
        results.append(
            {
                "doi": item.get("DOI", ""),
                "title": " ".join((item.get("title") or [""])[0].split()),
                "author": ", ".join(
                    f"{author.get('given', '')} {author.get('family', '')}".strip()
                    for author in item.get("author", [])
                ),
                "journal": " ".join((item.get("container-title") or [""])[0].split()),
                "url": item.get("URL") or "",
                "year": issued,
            }
        )
    return {"results": results, "note": ""}
