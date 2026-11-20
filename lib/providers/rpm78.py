"""rpm78 tier: Great 78 Project (archive.org collection:georgeblood).

~400k digitized 78rpm records (1898-1950s) - free streaming + download.
"""

from __future__ import annotations


def _playable(files: list) -> str:
    for name in files:
        filename = str(name.get("name") or "")
        if filename.lower().endswith((".mp3", ".ogg", ".flac", ".m4a")):
            return filename
    return ""


API = "https://archive.org/advancedsearch.php"


def search(query: str, limit: int = 20) -> dict:
    if not query.strip():
        raise ValueError("search must not be blank")
    rows = min(max(limit, 1), 40)
    response = http.get(
        API,
        params={
            "q": f"({query.strip()}) AND collection:(georgeblood)",
            "fl[]": "identifier,title,creator,date",
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
                "tier": "rpm78",
                "link": link,
                "snippet": f"78rpm record, {doc.get('date') or 'undated'}",
            }
        )
    return {"results": results[:limit], "note": ""}


import lib.providers.http as http  # noqa: E402