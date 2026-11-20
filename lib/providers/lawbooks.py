"""lawbooks tier: Internet Archive full law library.

Law dictionaries (incl. Black's Law editions), Blackstone's Commentaries,
statutes, case reporters, treatises, constitutions, legal history — the
public-domain law shelf of archive.org, searchable in one place.
"""
import urllib.parse

from lib.providers.http import POLITE_UA, get

_SUBJECTS = [
    '("law dictionary" OR "black\'s law" OR "blackstone" OR "common law" OR "case law" OR statutes OR jurisprudence)',
]


def search(query: str, limit: int = 25) -> dict:
    escaped = urllib.parse.quote(query)
    subject = _SUBJECTS[0]
    q = f'({escaped}) AND mediatype:(texts) AND ({subject})'
    params = {
        "q": q,
        "rows": str(limit),
        "output": "json",
        "fl[]": "identifier,title,creator,year",
        "sort[]": "downloads desc",
    }
    response = get("https://archive.org/advancedsearch.php", params=params, headers={"User-Agent": POLITE_UA}, timeout=45.0)
    if response is None or response.status_code != 200:
        return {"results": [], "note": "archive.org slow/blocked"}
    try:
        docs = response.json().get("response", {}).get("docs", [])
    except Exception:
        return {"results": [], "note": "archive.org returned unparseable response"}
    results = []
    for doc in docs:
        ident = str(doc.get("identifier") or "")
        if not ident:
            continue
        creator = doc.get("creator")
        creators = ", ".join(creator) if isinstance(creator, list) else str(creator or "")
        results.append(
            {
                "title": str(doc.get("title") or ident),
                "author": creators,
                "url": f"https://archive.org/details/{ident}",
                "tier": "lawbooks",
                "snippet": str(doc.get("year") or ""),
            }
        )
    return {"results": results[:limit], "note": "archive.org law library (dictionaries, reporters, treatises)"}