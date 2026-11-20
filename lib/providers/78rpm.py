"""78rpm tier: the Great 78 Project (archive.org georgeblood collection).

~400k digitized 78rpm records and cylinder recordings (1900s-1950s):
jazz, blues, classical, opera, marches, novelty — all streamable/downloadable.
"""
import urllib.parse

import httpx

API = "https://archive.org/advancedsearch.php"


def search(query: str, limit: int = 25) -> dict:
    try:
        cleaned = urllib.parse.quote(query)
        params = (
            f"q=(collection%3Ageorgeblood)+AND+{cleaned}"
            f"&fl%5B%5D=identifier&fl%5B%5D=title&fl%5B%5D=creator"
            f"&fl%5B%5D=year&sort%5B%5D=downloads+desc"
            f"&rows={min(limit, 60)}&page=1&output=json"
        )
        response = httpx.get(f"{API}?{params}", timeout=30.0, headers={"User-Agent": "research-hub/1.0"})
        docs = (response.json().get("response", {}) or {}).get("docs", []) or []
    except Exception:
        return {"results": [], "note": "archive.org search unavailable"}
    results = []
    for doc in docs[:limit]:
        ident = str(doc.get("identifier", "")).strip()
        if not ident:
            continue
        creator = doc.get("creator", "")
        creator = " & ".join(creator) if isinstance(creator, list) else str(creator)
        year = str(doc.get("year", ""))
        title = str(doc.get("title") or ident).replace("_", " ")
        if creator and creator.lower() not in title.lower():
            title = f"{title} — {creator}" if creator else title
        if year:
            title = f"{title} ({year})"
        results.append(
            {
                "title": title,
                "author": creator,
                "url": f"https://archive.org/details/{ident}",
                "tier": "78rpm",
            }
        )
    return {"results": results, "note": "78rpm/cylinder recordings, ~400k discs digitized"}