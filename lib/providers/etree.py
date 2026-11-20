"""etree tier: Live Music Archive (archive.org collection:etree).

Free streaming concert recordings ( trade-friendly bands ). Query text
matches titles/creators; results link to the item page and expose the
first playable audio file for the dashboard player.
"""

from __future__ import annotations

API = "https://archive.org/advancedsearch.php"


def _playable(files: list) -> str:
    for name in files:
        filename = str(name.get("name") or "")
        if filename.lower().endswith((".mp3", ".ogg", ".flac", ".m4a")):
            return filename
    return ""


def search(query: str, limit: int = 20) -> dict:
    if not query.strip():
        raise ValueError("search must not be blank")
    rows = min(max(limit, 1), 40)
    response = http.get(
        API,
        params={
            "q": f"({query.strip()}) AND collection:(etree)",
            "fl[]": "identifier,title,creator,year,downloads",
            "rows": rows,
            "page": 1,
            "output": "json",
        },
        timeout=30.0,
    )
    docs = response.json().get("response", {}).get("docs", [])
    results = []
    for doc in docs[: rows]:
        identifier = doc.get("identifier") or ""
        creator = doc.get("creator") or ""
        if isinstance(creator, list):
            creator = ", ".join(str(v) for v in creator)
        link = ""
        if identifier:
            try:
                detail = http.get(f"https://archive.org/metadata/{identifier}", timeout=20.0)
                name = _playable(detail.json().get("files", []))
                if name:
                    link = f"https://archive.org/download/{identifier}/{name}"
            except Exception:  # noqa: BLE001 - link is best effort
                link = ""
        results.append(
            {
                "title": str(doc.get("title") or identifier),
                "author": creator,
                "url": f"https://archive.org/details/{identifier}",
                "tier": "etree",
                "link": link,
                "snippet": f"Live concert recording, {doc.get('year') or 'undated'}",
            }
        )
    return {"results": results[:limit], "note": ""}


import lib.providers.http as http  # noqa: E402