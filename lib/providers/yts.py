"""YTS movie torrent index (JSON API)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from lib.providers._shadow import API_UA, ParseDrift, cache, clean, format_results, get_json

API = "https://yts.rs/api/v2/list_movies.json"
API_ORIGIN = "https://yts.rs"
MIRRORS = ("https://yts.rs", "https://yts.mx")
HEADERS = {"User-Agent": API_UA}
TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.tracker.cl:1337/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
)


def magnet_for(info_hash: str, name: str) -> str:
    return "magnet:?xt=urn:btih:{}&dn={}&tr={}".format(
        info_hash.lower(), quote(name, safe=""), "&tr=".join(TRACKERS)
    )


def _torrent_rows(movie: dict[str, Any]) -> list[dict[str, Any]]:
    title = clean(movie.get("title"))
    year = movie.get("year")
    genres = [
        clean(genre)
        for genre in (movie.get("genres") or [])
        if isinstance(genre, str) and clean(genre)
    ]
    rows = []
    for torrent in movie.get("torrents") or []:
        if not isinstance(torrent, dict):
            continue
        info_hash = clean(torrent.get("hash"))
        quality = clean(torrent.get("quality"))
        if not info_hash or not title:
            continue
        rows.append(
            {
                "title": f"{title} ({year}) [{quality}]" if year else f"{title} [{quality}]",
                "author": ", ".join(genres),
                "url": f"{API_ORIGIN}/torrent/download/{info_hash}",
                "link": magnet_for(info_hash, title),
                "snippet": "{} · {} seeds · {} peers".format(
                    clean(torrent.get("size")) or "unknown size",
                    torrent.get("seeds", 0),
                    torrent.get("peers", 0),
                ),
                "seeds": torrent.get("seeds", 0),
            }
        )
    return rows


def parse_response(payload: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    if isinstance(payload, dict) and payload.get("kind") == "transport-observation":
        note = str(payload.get("note") or "mirror-dead")
        if note in {"challenge", "cloudflare-403", "mirror-dead", "needs-key", "parse-drift"}:
            return {"results": [], "note": note}
        raise ParseDrift("invalid YTS transport observation")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ParseDrift("YTS response schema changed")
    movies = data.get("movies") or []
    if not isinstance(movies, list):
        raise ParseDrift("YTS response schema changed")
    rows = []
    for movie in movies:
        if isinstance(movie, dict):
            rows.extend(_torrent_rows(movie))
    rows.sort(key=lambda row: row.pop("seeds") or 0, reverse=True)
    return format_results(rows, limit)


@cache
def search(query: str, limit: int = 20) -> dict[str, Any]:
    payload = get_json(
        API,
        params={"query_term": query, "limit": 50, "sort_by": "seeds", "order_by": "desc"},
        headers=HEADERS,
        mirrors=MIRRORS,
    )
    return parse_response(payload, limit)


__all__ = ["magnet_for", "parse_response", "search"]