"""ccmixter tier: ccMixter remix community (Creative Commons music).

Query matches track names (upload_name_like) OR tags. Direct mp3 URLs
when the API exposes them; otherwise the file page.
"""

from __future__ import annotations

import http.client
import json as _json
import urllib.parse
import urllib.request

API = "https://ccmixter.org/api/query"


http.client._MAXLINE = 32 * 1024 * 1024


def _api(params: dict) -> list:
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read().decode("utf-8", "replace")
    data = _json.loads(body)
    return data if isinstance(data, list) else []


def _audio(item: dict) -> str:
    for candidate in item.get("files") or []:
        name = str(candidate.get("file_name") or "")
        if not name.lower().endswith((".mp3", ".ogg", ".m4a", ".flac")):
            continue
        raw = str(candidate.get("file_raw_url") or "")
        if raw:
            return raw if raw.startswith("http") else f"https://ccmixter.org{raw}"
        raw = str(candidate.get("download_url") or "")
        if raw:
            return raw if raw.startswith("http") else f"https://ccmixter.org{raw}"
        user = str(item.get("user_name") or "")
        if user:
            return f"https://ccmixter.org/content/{user}/{name}"
    return ""


def search(query: str, limit: int = 20) -> dict:
    if not query.strip():
        raise ValueError("search must not be blank")
    term = query.strip()
    rows = min(max(limit, 1), 40)
    items = _api({"upload_name_like": term, "limit": rows, "format": "json"})
    if not items:
        items = _api({"tags": term, "limit": rows, "format": "json"})
    results = []
    for item in items[: rows]:
        results.append(
            {
                "title": str(item.get("upload_name") or "untitled"),
                "author": str(item.get("user_real_name") or item.get("user_name") or ""),
                "url": str(item.get("file_page_url") or item.get("artist_page_url") or "https://ccmixter.org"),
                "tier": "ccmixter",                "link": _audio(item),
                "snippet": ", ".join(str(item.get("upload_tags") or "").split(",")[:4]),
            }
        )
    return {"results": results[:limit], "note": ""}

