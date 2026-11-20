"""3dprint tier: 3D-printable STL models on Wikimedia Commons (open, no API key).

Thingiverse and Printables both require OAuth tokens, so Commons is the open
backbone here; engraving-adjacent SVG cut files live in the engraving tier.
"""
import re

import lib.providers.http as http

API = "https://commons.wikimedia.org/w/api.php"


def search(query: str, limit: int = 20) -> dict:
    needle = " ".join(query.split()) or "model"
    response = http.get(
        API,
        params={
            "action": "query",
            "list": "search",
            "srsearch": f"{needle} filemime:application/sla",
            "srnamespace": "6",
            "srlimit": str(min(max(limit, 1), 50)),
            "format": "json",
        },
        timeout=30.0,
    )
    hits = response.json().get("query", {}).get("search", [])
    results = []
    for hit in hits:
        title = str(hit.get("title", ""))
        if not title.lower().endswith(".stl"):
            continue
        name = title.removeprefix("File:")
        results.append(
            {
                "title": name,
                "author": "",
                "url": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
                "snippet": re.sub(r"</?span[^>]*>", "", str(hit.get("snippet", ""))),
                "tier": "models3d",
            }
        )
    return {"results": results[:limit], "note": "open STL models on Wikimedia Commons (Thingiverse/Printables need their own API keys)"}
