"""wikisource tier: Wikisource full-text search (original documents, pre-1900 texts, historical records)."""
import html

import lib.providers.http as http

ENDPOINTS = {
    "en": "https://en.wikisource.org/w/api.php",
    "multilingual": "https://wikisource.org/w/api.php",
}


def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(
        ENDPOINTS["en"],
        params={
            "action": "query",
            "list": "search",
            "srsearch": query.strip(),
            "srlimit": min(max(limit, 1), 50),
            "format": "json",
        },
        timeout=30.0,
        polite=True,
    )
    results: list[dict[str, object]] = []
    for hit in response.json().get("query", {}).get("search", []):
        title = html.unescape(hit.get("title") or "")
        results.append(
            {
                "title": title,
                "author": "",
                "url": "https://en.wikisource.org/wiki/" + title.replace(" ", "_"),
                "snippet": html.unescape(hit.get("snippet") or "")
                .replace('<span class="searchmatch">', "")
                .replace("</span>", "")[:300],
                "link": "",
                "tier": "wikisource",
            }
        )
    return {"results": results[:limit], "note": ""}
