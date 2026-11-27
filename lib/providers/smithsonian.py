"""Smithsonian Open Access search API."""

from lib.providers._shadow import cache, credential_for, format_results, get_json

API = "https://api.si.edu/openaccess/api/v1.0/search"
MIRRORS = ("https://api.si.edu",)


def parse_response(payload: dict, limit: int = 20) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Smithsonian response is not an object")
    status = payload.get("http_status")
    body = payload.get("payload", payload)
    if status in (401, 403):
        error = body.get("error") if isinstance(body, dict) else None
        code = error.get("code") if isinstance(error, dict) else ""
        if code in {"API_KEY_MISSING", "API_KEY_INVALID"}:
            return {"results": [], "note": "needs-key"}
        return {"results": [], "note": "challenge"}
    if isinstance(status, int) and status >= 500:
        return {"results": [], "note": "mirror-dead"}
    response = body.get("response") if isinstance(body, dict) else None
    rows = response.get("rows") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Smithsonian response schema changed")
    results = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        title = " ".join(str(row.get("title") or "").split())
        content = row.get("content") if isinstance(row.get("content"), dict) else {}
        descriptive = content.get("descriptiveNonRepeating")
        if not isinstance(descriptive, dict):
            descriptive = {}
        url = str(descriptive.get("record_link") or row.get("id") or "").strip()
        freetext = content.get("freetext") if isinstance(content.get("freetext"), dict) else {}
        names = freetext.get("name", [])
        authors = [
            " ".join(str(name.get("content") or "").split())
            for name in names
            if isinstance(name, dict) and "author" in str(name.get("label") or "").casefold()
        ] if isinstance(names, list) else []
        if title and url:
            results.append(
                {
                    "title": title,
                    "author": ", ".join(name for name in authors if name),
                    "url": url,
                    "id": str(row.get("id") or ""),
                }
            )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict:
    key = credential_for("smithsonian")
    if not key:
        return {"results": [], "note": "needs-key"}
    payload = get_json(
        API,
        params={"q": query, "rows": limit, "api_key": key},
        mirrors=MIRRORS,
    )
    return parse_response(payload, limit)
