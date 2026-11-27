"""Nyaa torrent index (RSS)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

from lib.providers._shadow import (
    BROWSER_UA,
    ParseDrift,
    cache,
    clean,
    format_results,
    get_html,
)

API = "https://nyaa.si/"
MIRRORS = ("https://nyaa.si", "https://nyaa.land")
HEADERS = {"User-Agent": BROWSER_UA}
NYAA_NS = "https://nyaa.si/xmlns/nyaa"


def magnet_for(info_hash: str, name: str) -> str:
    return "magnet:?xt=urn:btih:{}&dn={}".format(info_hash.lower(), quote(name, safe=""))


def parse_response(rss_text: str, limit: int = 20) -> dict[str, Any]:
    if not isinstance(rss_text, str):
        raise ParseDrift("Nyaa response was not RSS text")
    if "just a moment" in rss_text[:4096].casefold():
        return {"results": [], "note": "challenge"}
    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError as error:
        raise ParseDrift("Nyaa response could not be parsed") from error
    if root.tag != "rss":
        raise ParseDrift("Nyaa response schema changed")
    results = []
    for item in root.iter("item"):
        title = clean(item.findtext("title"))
        url = clean(item.findtext("link"))
        if not title or not url or not url.startswith(("http://", "https://")):
            continue
        info_hash = clean(item.findtext(f"{{{NYAA_NS}}}infoHash"))
        category = clean(item.findtext(f"{{{NYAA_NS}}}category"))
        seeders = clean(item.findtext(f"{{{NYAA_NS}}}seeders")) or "0"
        leechers = clean(item.findtext(f"{{{NYAA_NS}}}leechers")) or "0"
        size = clean(item.findtext(f"{{{NYAA_NS}}}size"))
        link = magnet_for(info_hash, title) if info_hash else ""
        results.append(
            {
                "title": title,
                "author": category,
                "url": url,
                "link": link,
                "snippet": "{} · {} seeds · {} leechers".format(size or "unknown size", seeders, leechers),
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict[str, Any]:
    rss_text = get_html(
        API,
        params={"page": "rss", "q": query},
        headers=HEADERS,
        mirrors=MIRRORS,
    )
    return parse_response(rss_text, limit)


__all__ = ["magnet_for", "parse_response", "search"]