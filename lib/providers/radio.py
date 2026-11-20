"""radio_browser tier: worldwide live radio via the radio-browser.info community database.

search "jazz" finds stations by name; also supports "tag:ambient", "country:japan",
"genre:electronic" style prefixes so users can slice the 50k-station database.
"""
import httpx

from lib.providers.http import BROWSER_UA

API = "https://de1.api.radio-browser.info/json"
HEADERS = {"User-Agent": BROWSER_UA}


def search(query: str, limit: int = 20) -> dict:
    query = (query or "").strip()
    if not query:
        return {"results": [], "note": "empty query"}
    field, term = "byname", query
    lowered = query.lower()
    if lowered.startswith("tag:"):
        field, term = "bytag", query[4:]
    elif lowered.startswith("country:"):
        field, term = "bycountrycodeexact", query[8:]
    elif lowered.startswith("genre:"):
        field, term = "bytag", query[6:]
    path = term.replace(" ", "%20")
    try:
        response = httpx.post(
            f"{API}/stations/{field}/{path}",
            json={"limit": max(min(limit, 50), 1), "hidebroken": "true"},
            timeout=30.0,
            headers=HEADERS,
        )
        response.raise_for_status()
        stations = response.json()
    except Exception as error:
        return {"results": [], "note": f"radio-browser error: {error.__class__.__name__}"}
    results = []
    for station in stations[:limit]:
        name = str(station.get("name") or "").strip()
        stream = station.get("url_resolved") or station.get("url") or ""
        codec = (station.get("codec") or "").upper()
        bitrate = station.get("bitrate") or ""
        tags = ", ".join((station.get("tags") or "").split(",")[:3])
        country = station.get("country") or ""
        home = station.get("homepage") or ""
        detail = " • ".join(x for x in (codec, bitrate and f"{bitrate} kbps", tags) if x)
        results.append(
            {
                "title": name or "Unknown station",
                "author": country,
                "url": home or "https://www.radio-browser.info",
                "link": stream,
                "snippet": detail,
            }
        )
    return {"results": results, "note": "live streams — press the Stream button"}