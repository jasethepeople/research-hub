from __future__ import annotations

from typing import Any
from urllib.parse import quote

from lib.providers._shadow import API_UA, ParseDrift, cache, clean, format_results, get_json

API = "https://api.datacite.org/dois"
MIRRORS = ("https://api.datacite.org",)
HEADERS = {"User-Agent": API_UA}


def parse_response(payload: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("kind") == "transport-observation":
        note = str(payload.get("note") or "mirror-dead")
        if note in {"challenge", "cloudflare-403", "mirror-dead", "needs-key", "parse-drift"}:
            return {"results": [], "note": note}
        raise ParseDrift("invalid DataCite transport observation")
    records = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ParseDrift("DataCite response schema changed")
    results = []
    for record in records:
        if not isinstance(record, dict):
            continue
        attributes = record.get("attributes")
        if not isinstance(attributes, dict):
            continue
        doi = clean(attributes.get("doi") or record.get("id"))
        titles = attributes.get("titles") or []
        title = next(
            (clean(item.get("title")) for item in titles if isinstance(item, dict) and clean(item.get("title"))),
            "",
        )
        if not doi or not title:
            continue
        creators = attributes.get("creators") or []
        authors = [
            clean(creator.get("name"))
            for creator in creators
            if isinstance(creator, dict) and clean(creator.get("name"))
        ]
        types = attributes.get("types")
        publisher = attributes.get("publisher")
        if isinstance(publisher, dict):
            publisher = publisher.get("name")
        results.append(
            {
                "doi": doi,
                "title": title,
                "author": ", ".join(authors),
                "url": f"https://doi.org/{quote(doi, safe='/')}",
                "year": str(attributes.get("publicationYear") or ""),
                "publisher": clean(publisher),
                "resource_type": clean(types.get("resourceTypeGeneral")) if isinstance(types, dict) else "",
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict[str, Any]:
    payload = get_json(
        API,
        params={"query": query, "page[size]": limit, "page[number]": 1, "disable-facets": "true"},
        headers=HEADERS,
        mirrors=MIRRORS,
    )
    return parse_response(payload, limit)


__all__ = ["parse_response", "search"]
