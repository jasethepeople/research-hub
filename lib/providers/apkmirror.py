"""APKMirror tier: grey-market Android application archive search."""

import re
from typing import Any

from lib.providers.http import BROWSER_UA, get

BASE = "https://www.apkmirror.com"
ROW = re.compile(
    r'<h5[^>]*class="appRowTitle[^"]*"[^>]*>\s*<a[^>]+href="(/apk/[^"]+)"[^>]*>(.*?)</a>',
    re.S,
)
DEVELOPER = re.compile(r'class="byDeveloper[^"]*"[^>]*>(?:by )?([^<]+)<')


def _clean(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", "", value).split())


def search(query: str, limit: int = 20) -> dict[str, Any]:
    response = get(
        BASE,
        pairs=[["post_type", "app_release"], ["searchtype", "apk"], ["s", query.strip()]],
        headers={"User-Agent": BROWSER_UA},
        timeout=30.0,
    )
    results = []
    seen: set[str] = set()
    for match in ROW.finditer(response.text):
        path, title = match.group(1), _clean(match.group(2))
        if not title or path in seen:
            continue
        seen.add(path)
        dev = ""
        tail = response.text[match.end() : match.end() + 600]
        dev_match = DEVELOPER.search(tail)
        if dev_match:
            dev = _clean(dev_match.group(1))
        results.append(
            {
                "title": title[:200],
                "url": f"{BASE}{path}",
                "author": dev,
                "published": "",
                "source": "APKMirror",
                "id": path,
            }
        )
        if len(results) >= max(limit, 1):
            break
    return {"results": results, "note": ""}