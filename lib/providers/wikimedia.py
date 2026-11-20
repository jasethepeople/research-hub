"""wikimedia tier: Wikimedia Commons image & video search."""
from typing import Any

import lib.providers.http as http

API = "https://commons.wikimedia.org/w/api.php"


def _search(needle: str, gsrsearch: str, limit: int) -> dict[str, Any]:
    response = http.get(
        API,
        params={
            "action": "query",
            "generator": "search",
            "gsrsearch": gsrsearch,
            "gsrnamespace": 6,
            "gsrlimit": min(max(limit, 1), 50),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": 480,
            "format": "json",
        },
        timeout=30.0,
    )
    pages = response.json().get("query", {}).get("pages", {})
    results = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 9)):
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("url") or ""
        if not url:
            continue
        results.append(
            {
                "title": str(page.get("title") or "").replace("File:", ""),
                "author": ((info.get("extmetadata") or {}).get("Artist") or {}).get("value", ""),
                "url": info.get("descriptionurl") or url,
                "link": info.get("thumburl") or url,
                "snippet": f"{info.get('width', 0)}x{info.get('height', 0)} · Wikimedia Commons",
            }
        )
    return {"results": results, "note": ""}


def search(query: str, limit: int = 20) -> dict[str, Any]:
    return _search(query, f"{query.strip()} filetype:bitmap", limit)


def search_video(query: str, limit: int = 20) -> dict[str, Any]:
    return _search(query, f"{query.strip()} filetype:video", limit)