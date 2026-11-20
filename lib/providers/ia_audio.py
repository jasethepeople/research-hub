"""ia_audio tier: Internet Archive audio — concerts, records, radio, spoken word."""
import lib.providers.http as http

API = "https://archive.org/advancedsearch.php"


def _playable(files: list[dict]) -> str:
    names = [f.get("name") or "" for f in files]
    for ext in (".mp3", ".ogg", ".flac", ".m4a"):
        for name in names:
            if name.endswith(f"64kb{ext}"):
                return name
    for ext in (".mp3", ".ogg", ".flac", ".m4a"):
        for name in names:
            if name.lower().endswith(ext):
                return name
    return ""


def _creator(value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value or "")

def search(query: str, limit: int = 20) -> dict:
    if not query.strip():
        raise ValueError("search must not be blank")
    rows = min(max(limit, 1), 40)
    response = http.get(
        API,
        params={
            "q": f"({query.strip()}) AND mediatype:(audio)",
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
        link = ""
        if identifier:
            try:
                detail = http.get(
                    f"https://archive.org/metadata/{identifier}", timeout=20.0
                )
                name = _playable(detail.json().get("files", []))
                if name:
                    link = f"https://archive.org/download/{identifier}/{name}"
            except Exception:  # noqa: BLE001 - link is best effort
                link = ""
        results.append(
            {
                "title": str(doc.get("title") or identifier),
                "author": _creator(doc.get("creator")),
                "url": f"https://archive.org/details/{identifier}",
                "link": link,
                "snippet": str(doc.get("year") or ""),
            }
        )
    return {"results": results, "note": ""}
