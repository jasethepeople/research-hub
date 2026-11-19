"""librivox tier."""
import re
import xml.etree.ElementTree as ET

import lib.providers.http as http

API = "https://librivox.org/api/feed/audiobooks"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get("https://librivox.org/rss/latest_releases", timeout=30.0)
    root = ET.fromstring(response.content)
    needle = query.strip().lower()
    results: list[dict[str, object]] = []
    for item in root.iter("item"):
        title = re.sub(r"^CDATA\[|\]\]>$", "", (item.findtext("title") or "").strip())
        if needle and needle not in title.lower():
            continue
        link = (item.findtext("link") or "").strip()
        text = re.sub(r"<[^>]+>", " ", (item.findtext("description") or ""))
        text = re.sub(r"\s+", " ", text).strip()
        results.append({
            "title": title,
            "author": "",
            "url": link,
            "snippet": text[:300],
        })
        if len(results) >= limit:
            break
    return {"results": results, "note": "" if results else "no matches in latest releases feed"}
