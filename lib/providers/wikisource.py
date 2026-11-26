from __future__ import annotations

from typing import Any
from urllib.parse import quote

from lib.providers._shadow import API_UA, cache, format_results, get_json

API = "https://en.wikisource.org/w/api.php"
MIRRORS = ("https://en.wikisource.org",)


def parse_response(payload: Any, limit: int = 20) -> dict[str, Any]:
    query = payload.get("query") if isinstance(payload, dict) else None
    matches = query.get("search") if isinstance(query, dict) else None
    if not isinstance(matches, list):
        raise ValueError("invalid Wikisource search response")
    results = []
    for match in matches:
        if not isinstance(match, dict):
            continue
        title = str(match.get("title") or "").strip()
        if not title:
            continue
        page_id = match.get("pageid")
        if isinstance(page_id, int) and page_id > 0:
            url = f"https://en.wikisource.org/w/index.php?curid={page_id}"
        else:
            url = f"https://en.wikisource.org/wiki/{quote(title.replace(' ', '_'), safe='():,_-')}"
        item: dict[str, Any] = {"title": title, "url": url}
        timestamp = str(match.get("timestamp") or "")[:4]
        if timestamp.isdigit():
            item["year"] = int(timestamp)
        results.append(item)
    return format_results(results, limit)


@cache

def search(query: str, limit: int = 20) -> dict[str, Any]:
    bounded_limit = min(max(int(limit), 1), 50)
    normalized = str(query).strip()
    payload = get_json(
        API,
        params={
            "action": "query",
            "list": "search",
            "srsearch": normalized,
            "srnamespace": 0,
            "srlimit": bounded_limit,
            "srprop": "timestamp",
            "format": "json",
            "formatversion": 2,
        },
        headers={"User-Agent": API_UA},
        mirrors=MIRRORS,
    )
    return parse_response(payload, bounded_limit)


__all__ = ["parse_response", "search"]
