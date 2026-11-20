"""gutenberg tier: Project Gutenberg book search (70k+ free ebooks, incl. old law/science texts)."""
import re

SEARCH = "https://www.gutenberg.org/ebooks/search/"

_UA_OVERRIDES = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-hub"}


def search(query: str, limit: int = 20) -> dict[str, object]:
    response = httpx_get(SEARCH, params={"query": query.strip()})
    results: list[dict[str, object]] = []
    for match in re.finditer(
        r'<a href="/ebooks/(\d+)/?"[^>]*>\s*([^<]+?)\s*</a>', response.text
    ):
        book_id, title = match.group(1), match.group(2)
        results.append(
            {
                "title": title,
                "author": "",
                "url": f"https://www.gutenberg.org/ebooks/{book_id}",
                "link": "",
                "tier": "gutenberg",
            }
        )
        if len(results) >= limit:
            break
    note = "" if results else "Gutenberg search page returned no matches or is rate-limiting"
    return {"results": results[:limit], "note": note}


def httpx_get(url: str, params: dict | None = None):
    import httpx

    last = None
    for _ in range(3):
        try:
            response = httpx.get(
                url,
                params=params,
                timeout=30.0,
                headers=_UA_OVERRIDES,
                follow_redirects=True,
            )
            if response.status_code == 200:
                return response
        except Exception as error:
            last = error
        import time

        time.sleep(1.0)
    if last:
        raise last
    return response
