from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from lib.providers._shadow import API_UA, ParseDrift, cache, clean, format_results, get_json, throttle

API = "https://doaj.org/api/search/articles/"
MIRRORS = ("https://doaj.org",)
HEADERS = {"User-Agent": API_UA}
MIN_REQUEST_INTERVAL = 1.1
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def parse_response(payload: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("kind") == "transport-observation":
        note = str(payload.get("note") or "mirror-dead")
        if note in {"challenge", "cloudflare-403", "mirror-dead", "needs-key", "parse-drift"}:
            return {"results": [], "note": note}
        raise ParseDrift("invalid DOAJ transport observation")
    records = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ParseDrift("DOAJ response schema changed")
    results = []
    for hit in records:
        if not isinstance(hit, dict):
            continue
        bibjson = hit.get("bibjson")
        if not isinstance(bibjson, dict):
            continue
        title = clean(bibjson.get("title"))
        identifier = clean(hit.get("id"))
        if not title or not ID_RE.fullmatch(identifier):
            continue
        authors = bibjson.get("author") or []
        author_names = [
            clean(item.get("name"))
            for item in authors
            if isinstance(item, dict) and clean(item.get("name"))
        ]
        journal = bibjson.get("journal")
        journal_title = clean(journal.get("title")) if isinstance(journal, dict) else ""
        doi = next(
            (
                clean(item.get("id"))
                for item in bibjson.get("identifier", [])
                if isinstance(item, dict)
                and clean(item.get("type")).casefold() == "doi"
                and clean(item.get("id"))
            ),
            "",
        )
        results.append(
            {
                "title": title,
                "author": ", ".join(author_names[:5]),
                "url": f"https://doaj.org/article/{quote(identifier, safe='')}",
                "journal": journal_title,
                "year": clean(bibjson.get("year")),
                "doi": doi,
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict[str, Any]:
    throttle("doaj", MIN_REQUEST_INTERVAL)
    payload = get_json(
        f"{API}{quote(query, safe='')}",
        params={"pageSize": limit},
        headers=HEADERS,
        mirrors=MIRRORS,
    )
    return parse_response(payload, limit)


__all__ = ["parse_response", "search"]
