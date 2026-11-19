"""LibGen tier: shadow library search scraped from libgen.li (no key required)."""

import re
from html.parser import HTMLParser

import httpx

MIRROR = "https://libgen.li"
SEARCH_URL = f"{MIRROR}/index.php"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
MD5_RE = re.compile(r"md5=([0-9a-fA-F]{32})")


class _RowsParser(HTMLParser):
    """Collect result-table rows (those containing an md5 link) as cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict]] = []
        self._row: list[dict] | None = None
        self._cell: dict | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = {"parts": [], "hrefs": []}
        elif tag == "a" and self._cell is not None:
            href = dict(attrs).get("href") or ""
            if href:
                self._cell["hrefs"].append(href)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._cell["text"] = " ".join("".join(self._cell["parts"]).split())
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any("md5=" in href for entry in self._row for href in entry["hrefs"]):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["parts"].append(data)
    def parse(self, html_text: str) -> list[list[dict]]:
        try:
            self.feed(html_text)
            self.close()
        except Exception:
            return self.rows
        return self.rows


def search(query: str, limit: int = 20) -> dict:
    response = httpx.get(
        SEARCH_URL,
        params={"req": query.strip(), "res": min(max(limit, 1), 50)},
        timeout=30.0,
        headers={"User-Agent": UA},
        follow_redirects=True,
    )
    response.raise_for_status()
    if "Library Genesis" not in response.text:
        return {"results": [], "note": "mirror returned an unexpected page"}
    results: list[dict] = []
    seen: set[str] = set()
    for row in _RowsParser().parse(response.text):
        if len(row) < 9:
            continue
        md5 = next(
            (
                match.group(1).lower()
                for entry in row
                for href in entry["hrefs"]
                if (match := MD5_RE.search(href))
            ),
            "",
        )
        if not md5 or md5 in seen:
            continue
        seen.add(md5)
        results.append(
            {
                "md5": md5,
                "title": row[0]["text"],
                "author": row[1]["text"],
                "url": f"{MIRROR}/ads.php?md5={md5}",
                "publisher": row[2]["text"],
                "year": row[3]["text"],
                "language": row[4]["text"],
                "size": row[6]["text"],
                "format": row[7]["text"].upper(),
                "annas": next(
                    (href for entry in row for href in entry["hrefs"] if "annas-archive" in href),
                    "",
                ),
            }
        )
        if len(results) >= limit:
            break
    return {"results": results, "note": "" if results else "no parsable results"}
