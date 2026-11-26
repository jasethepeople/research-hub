from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from lib.providers._shadow import API_UA, ParseDrift, cache, clean, format_results, get_html

API = "https://libgen.li/index.php"
MIRRORS = (
    "https://libgen.la",
    "https://libgen.rs",
    "https://libgen.is",
    "https://libgen.st",
    "https://libgen.gs",
)
MD5_RE = re.compile(r"md5=([0-9a-fA-F]{32})")
CHALLENGE_RE = re.compile(
    r"cf-chl|captcha|access denied|verify you are human|<title>\s*just a moment",
    re.I,
)


class _RowsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, Any]]] = []
        self._row: list[dict[str, Any]] | None = None
        self._cell: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = {"parts": [], "hrefs": []}
        elif tag == "a" and self._cell is not None:
            href = dict(attrs).get("href") or ""
            if href:
                self._cell["hrefs"].append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._cell["text"] = clean("".join(self._cell["parts"]))
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any("md5=" in href for cell in self._row for href in cell["hrefs"]):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["parts"].append(data)


def parse_response(payload: str | dict[str, Any], limit: int = 20) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("kind") == "transport-observation":
        note = str(payload.get("note") or "mirror-dead")
        if note in {"challenge", "cloudflare-403", "mirror-dead", "needs-key", "parse-drift"}:
            return {"results": [], "note": note}
        raise ParseDrift("invalid LibGen transport observation")
    if not isinstance(payload, str):
        raise ParseDrift("LibGen response was not HTML text")
    if CHALLENGE_RE.search(payload):
        return {"results": [], "note": "challenge"}
    if "Library Genesis" not in payload or "<table" not in payload.lower():
        raise ParseDrift("LibGen search markup changed")
    response_url = str(getattr(payload, "url", "") or API)
    parts = urlsplit(response_url)
    base_url = f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else "https://libgen.li"
    parser = _RowsParser()
    try:
        parser.feed(payload)
        parser.close()
    except Exception as error:
        raise ParseDrift("LibGen search markup could not be parsed") from error
    results = []
    seen = set()
    for row in parser.rows:
        if len(row) < 9:
            continue
        md5 = next(
            (
                match.group(1).lower()
                for cell in row
                for href in cell["hrefs"]
                if (match := MD5_RE.search(href))
            ),
            "",
        )
        title = clean(row[0]["text"])
        if not md5 or md5 in seen or not title:
            continue
        seen.add(md5)
        results.append(
            {
                "md5": md5,
                "title": title,
                "author": clean(row[1]["text"]),
                "url": f"{base_url}/ads.php?md5={md5}",
                "publisher": clean(row[2]["text"]),
                "year": clean(row[3]["text"]),
                "language": clean(row[4]["text"]),
                "format": clean(row[7]["text"]).upper(),
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict[str, Any]:
    page = get_html(
        API,
        params={"req": query, "res": limit, "view": "simple", "column": "def"},
        headers={"User-Agent": API_UA},
        mirrors=MIRRORS,
    )
    return parse_response(page, limit)


__all__ = ["parse_response", "search"]
