"""radio_browser tier: community directory of live radio stations worldwide."""
import lib.providers.http as http

BASES = (
    "https://de1.api.radio-browser.info",
    "https://fi1.api.radio-browser.info",
    "https://de2.api.radio-browser.info",
)


def search(query: str, limit: int = 20) -> dict:
    if not query.strip():
        raise ValueError("search must not be blank")
    last_error: Exception | None = None
    for base in BASES:
        try:
            response = http.get(
                f"{base}/json/stations/search",
                params={
                    "name": query.strip(),
                    "limit": min(max(limit, 1), 50),
                    "hidebroken": "true",
                },
                timeout=20.0,
            )
            break
        except Exception as error:  # noqa: BLE001 - try next mirror
            last_error = error
    else:
        return {"results": [], "note": f"radio-browser mirrors unreachable: {last_error.__class__.__name__}"}
    results = []
    for station in response.json():
        codec = (station.get("codec") or "").strip()
        bitrate = (station.get("bitrate") or "").strip()
        quality = " ".join(part for part in (codec, f"{bitrate}kbps" if bitrate else "") if part)
        tags = ", ".join((station.get("tags") or "").split(",")[:4])
        stream = station.get("url_resolved") or station.get("url") or ""
        results.append(
            {
                "title": (station.get("name") or "").strip(),
                "author": " · ".join(part for part in (quality, station.get("country") or "") if part),
                "url": station.get("homepage") or stream,
                "link": stream,
                "snippet": tags,
            }
        )
    return {"results": results, "note": ""}
