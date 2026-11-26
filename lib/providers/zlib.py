from __future__ import annotations

import os
from urllib.parse import urlsplit

from lib.providers._shadow import BROWSER_UA, ParseDrift, cache, clean, credential_for, format_results, get_json


def parse_response(payload: object, limit: int = 20, search_url: str = "") -> dict:
    if isinstance(payload, dict) and payload.get("kind") == "transport-observation":
        note = str(payload.get("note") or "needs-key")
        return {"results": [], "note": note}
    if not isinstance(payload, dict):
        raise ParseDrift("Z-Library response was not an object")
    rows = next((payload.get(key) for key in ("results", "books", "data") if isinstance(payload.get(key), list)), None)
    if rows is None:
        raise ParseDrift("Z-Library response has no results list")
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = clean(row.get("title") or row.get("name"))
        if not title:
            continue
        url = str(row.get("metadata_url") or row.get("url") or row.get("link") or "").strip()
        parts = urlsplit(url)
        lower_url = url.casefold()
        if (
            parts.scheme not in {"http", "https"}
            or not parts.netloc
            or any(token in lower_url for token in ("download", ".pdf", ".epub", ".mobi", "/get/"))
        ):
            url = search_url
        if not url:
            continue
        author_value = row.get("author") or row.get("authors") or ""
        if isinstance(author_value, list):
            author_value = ", ".join(clean(value.get("name") if isinstance(value, dict) else value) for value in author_value)
        item = {"title": title, "url": url}
        if clean(author_value):
            item["author"] = clean(author_value)
        year = row.get("year") or row.get("published")
        if year:
            item["year"] = clean(year)
        results.append(item)
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict:
    key = credential_for("zlib")
    search_url = os.environ.get("HUB_TIER_ZLIB__SEARCH_URL", "").strip()
    if not key or not search_url:
        return {"results": [], "note": "needs-key"}
    parts = urlsplit(search_url)
    if parts.scheme != "https" or not parts.netloc:
        return {"results": [], "note": "needs-key"}
    payload = get_json(
        search_url,
        params={"q": query, "limit": limit},
        headers={"User-Agent": BROWSER_UA, "Authorization": f"Bearer {key}"},
        mirrors=(f"{parts.scheme}://{parts.netloc}",),
    )
    return parse_response(payload, limit, search_url)


__all__ = ["parse_response", "search"]
