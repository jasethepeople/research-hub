"""podcasts tier: Apple iTunes Search — every podcast in their public directory.

search "term" finds shows; "term ep:" finds recent episodes of that show.
Direct audio links (m4a/mp3) so the dashboard player can stream episodes inline.
"""
import re

import httpx

from lib.providers.http import BROWSER_UA

API = "https://itunes.apple.com/search"
_head_cache: dict[str, tuple[float, str]] = {}
HEAD_TTL = 86400.0


def _episode_audio(feed_url: str, limit: int) -> list[dict]:
    feed = httpx.get(feed_url, timeout=30.0, headers={"User-Agent": BROWSER_UA}, follow_redirects=True)
    items = re.findall(r"<item[ >].*?</item>", feed.text, re.S)[: max(limit, 1)]
    results: list[dict] = []
    for item in items:
        title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.S)
        enclosure = re.search(r'enclosure[^>]*url="([^"]+)"', item)
        pub_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
        if not (title_m and enclosure):
            continue
        results.append(
            {
                "title": title_m.group(1)[:200],
                "author": "episode",
                "url": enclosure.group(1),
                "link": enclosure.group(1),
                "snippet": (pub_m.group(1) if pub_m else "")[:40],
            }
        )
    return results


def search(query: str, limit: int = 20) -> dict:
    query = (query or "").strip()
    if not query:
        return {"results": [], "note": "empty query"}
    want_episodes = " ep:" in query.lower()
    show_query = re.sub(r"\s+ep:", "", query, flags=re.I).strip() or query
    try:
        response = httpx.get(
            API,
            params={
                "term": show_query,
                "media": "podcast",
                "entity": "podcast",
                "limit": max(min(limit, 50), 1),
            },
            timeout=30.0,
            headers={"User-Agent": BROWSER_UA},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as error:
        return {"results": [], "note": f"itunes error: {error.__class__.__name__}"}
    results = []
    for hit in payload.get("results", []):
        feed = hit.get("feedUrl") or ""
        art = (hit.get("artworkUrl600") or "").replace("600x600", "300x300")
        if want_episodes and feed:
            episodes = _episode_audio(feed, min(limit, 10))
            for ep in episodes:
                ep["tier"] = "podcasts"
            if episodes:
                return {"results": episodes, "note": "latest episodes"}
            continue
        results.append(
            {
                "title": str(hit.get("collectionName") or "Untitled show"),
                "author": str(hit.get("artistName") or ""),
                "url": str(hit.get("collectionViewUrl") or feed),
                "link": feed or art,
                "snippet": (str(hit.get("primaryGenreName") or "") + " • podcast"),
            }
        )
    return {"results": results[:limit], "note": ""}