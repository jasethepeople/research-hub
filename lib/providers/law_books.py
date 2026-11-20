"""law_books tier: Internet Archive legal-texts corpus.

Searches the IA full-text corpus for law dictionaries (all Black's Law
editions), common-law treatises, statutes, court reporters, and legal
histories. Downloadable as PDF/text via the archive resolver.
"""
import urllib.parse

from lib.providers.http import POLITE_UA, get


def search(query: str, limit: int = 25) -> dict:
    escaped = urllib.parse.quote(query)
    pairs = [
        (f'("{escaped}") AND subject:(law) AND mediatype:texts -collection:(magazine_rack)', None),
        (
            f'({escaped}) AND (title:("law dictionary" OR "blacks law" OR "blackstone" '
            f'OR "statutes" OR "commentaries" OR "case law"))'
            f' AND mediatype:texts -collection:(magazine_rack)',
            None,
        ),
    ]
    results: list[dict] = []
    note = ""
    for q, _ in pairs:
        params = {"q": q, "rows": str(limit), "output": "json", "fl[]": "identifier,title,creator,year", "sort[]": "downloads desc"}
        response = get("https://archive.org/advancedsearch.php", params=params, headers={"User-Agent": POLITE_UA}, timeout=45.0)
        if response is None or response.status_code != 200:
            note = "archive.org slow/blocked"
            continue
        try:
            docs = response.json().get("response", {}).get("docs", [])
        except Exception:
            note = "archive.org returned unparseable response"
            continue
        for doc in docs:
            ident = str(doc.get("identifier") or "")
            if not ident or any(r["url"] == f"https://archive.org/details/{ident}" for r in results):
                continue
            creator = doc.get("creator")
            creators = ", ".join(creator) if isinstance(creator, list) else str(creator or "")
            results.append(
                {
                    "title": str(doc.get("title") or ident),
                    "author": creators,
                    "url": f"https://archive.org/details/{ident}",
                    "tier": "law-books",
                    "snippet": str(doc.get("year") or ""),
                }
            )
        if results:
            note = "Internet Archive legal-texts corpus"
            break
    return {"results": results[:limit], "note": note}