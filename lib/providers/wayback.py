"""wayback tier: Wayback Machine capture lookup (works on URLs or domains)."""
import urllib.parse

import lib.providers.http as http

CDX = "https://web.archive.org/cdx/search/cdx"


def _rows(response) -> list:
    try:
        data = response.json()
    except ValueError:
        return []
    return data[1:] if isinstance(data, list) and len(data) > 1 else []


def _cards(rows: list, note: str) -> dict:
    results = [
        {
            "title": f"{row[1]} @ {str(row[0])[:8]}",
            "author": str(row[3] or "page"),
            "url": f"https://web.archive.org/web/{row[0]}/{row[1]}",
            "snippet": f"status {row[2]}" if len(row) > 2 else "",
            "tier": "wayback",
        }
        for row in rows
    ]
    return {"results": results, "note": note}


def search(query: str, limit: int = 20) -> dict:
    needle = query.strip()
    if not needle:
        return {"results": [], "note": "empty query"}
    fl = [("fl[]", name) for name in ("timestamp", "original", "statuscode", "mimetype")]
    if needle.startswith("http"):
        response = http.get(
            CDX,
            params={"url": needle, "output": "json", "limit": str(min(max(limit, 1), 50))},
            pairs=fl,
            polite=False,
            timeout=60.0,
        )
        return _cards(_rows(response), "Wayback captures of this URL")
    if "." not in needle:
        return {
            "results": [],
            "note": "enter a URL or domain (e.g. example.com) — Wayback indexes pages, not keywords",
        }
    response = http.get(
        CDX,
        params={
            "url": urllib.parse.quote(needle),
            "matchType": "domain",
            "output": "json",
            "collapse": "urlkey",
            "limit": str(min(max(limit, 1), 50)),
        },
        pairs=fl,
        polite=False,
        timeout=90.0,
    )
    return _cards(_rows(response), f"Wayback captures under {needle}")
