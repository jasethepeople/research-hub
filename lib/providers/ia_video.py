"""ia-video tier: Archive.org moving-image collection (public films, news, shorts)."""
from typing import Any

import lib.providers.http as http

API = "https://archive.org/advancedsearch.php"


def search(query: str, limit: int = 20) -> dict[str, Any]:
    response = http.get(
        API,
        params={
            "q": f'({query.strip()}) AND mediatype:(movies)',
            "fl[]": "identifier,title,description,downloads",
            "rows": min(max(limit, 1), 50),
            "page": 1,
            "output": "json",
        },
        timeout=30.0,
    )
    docs = response.json().get("response", {}).get("docs", [])
    results = []
    for doc in docs[:limit]:
        ident = doc.get("identifier", "")
        title = doc.get("title") or ident
        desc = doc.get("description") or ""
        if isinstance(desc, list):
            desc = " ".join(str(part) for part in desc)
        results.append(
            {
                "title": str(title)[:300],
                "author": "archive.org",
                "url": f"https://archive.org/details/{ident}",
                "link": f"https://archive.org/download/{ident}/{ident}_512kb.mp4",
                "snippet": str(desc).replace("\n", " ")[:300],
                "tier": "ia-video",
                "image": f"https://archive.org/services/img/{ident}",
            }
        )
    return {"results": results, "note": ""}
