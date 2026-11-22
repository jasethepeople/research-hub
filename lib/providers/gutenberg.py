"""Project Gutenberg public-domain catalog via the Gutendex JSON API."""

from lib.providers._shadow import API_UA, cache, format_results, get_json

API = "https://gutendex.com/books/"
MIRRORS = ("https://gutendex.com",)
HEADERS = {"User-Agent": API_UA}


def parse_response(payload: dict, limit: int = 20) -> dict:
    if isinstance(payload, dict) and payload.get("kind") == "transport-observation":
        note = str(payload.get("note") or "mirror-dead")
        if note in {"challenge", "cloudflare-403", "mirror-dead", "needs-key", "parse-drift"}:
            return {"results": [], "note": note}
        raise ValueError("invalid Gutendex transport observation")
    records = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("Gutendex response schema changed")
    results = []
    for book in records:
        if not isinstance(book, dict) or book.get("copyright") is not False:
            continue
        identifier = book.get("id")
        title = " ".join(str(book.get("title") or "").split())
        authors = [
            " ".join(str(author.get("name") or "").split())
            for author in book.get("authors", [])
            if isinstance(author, dict)
        ]
        if not title or not isinstance(identifier, int):
            continue
        results.append(
            {
                "title": title,
                "author": ", ".join(name for name in authors if name),
                "url": f"https://www.gutenberg.org/ebooks/{identifier}",
                "id": identifier,
                "languages": list(book.get("languages") or []),
                "subjects": list(book.get("subjects") or [])[:8],
                "downloads": book.get("download_count"),
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict:
    payload = get_json(
        API,
        params={"search": query, "copyright": "false", "page_size": limit},
        headers=HEADERS,
        mirrors=MIRRORS,
    )
    return parse_response(payload, limit)
