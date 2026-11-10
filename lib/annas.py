"""Anna's Archive research tier logic: sign-in, search parsing, and capped downloads."""

import json
import os
import re
import time
from collections import OrderedDict
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

import httpx

DEFAULT_MIRROR = "https://annas-archive.gd"
CACHE_TTL = 900
CACHE_MAX_ENTRIES = 200
DOWNLOAD_CAP = 250 * 1024 * 1024
MD5_HREF = re.compile(r"^/md5/([0-9a-fA-F]{32})$")
CHALLENGE_MARKS = ("captcha", "cf-browser-verification", "just a moment", "challenge")
DETAIL_SEPARATOR = "·"


class ChallengeEncountered(RuntimeError):
    """Raised internally when the mirror answers with a login/captcha challenge."""


def default_store_dir() -> Path:
    state = os.environ.get("HUB_STATE") or "~/.local/share/intel-hub"
    return Path(state).expanduser() / "annas-store"


def _clean(value: str) -> str:
    return " ".join(value.split())


class _CardParser(HTMLParser):
    """Collects anchors and the text nodes that follow each anchor, in document order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchor_events: list[tuple[str, str, int, int]] = []  # (href, inner_text, text_start, text_end)
        self.text_nodes: list[str] = []
        self._open_anchor: tuple[str, int] | None = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        if self._open_anchor is not None:
            self._close_anchor()
        href = dict(attrs).get("href") or ""
        self._open_anchor = (href, len(self.text_nodes))

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._open_anchor is not None:
            self._close_anchor()

    def _close_anchor(self):
        href, start = self._open_anchor
        end = len(self.text_nodes)
        text = _clean(" ".join(self.text_nodes[start:end]))
        self.anchor_events.append((href, text, start, end))
        self._open_anchor = None

    def close(self):
        if self._open_anchor is not None:
            self._close_anchor()
        super().close()

    def handle_data(self, data):
        stripped = _clean(data)
        if stripped:
            self.text_nodes.append(stripped)


def parse_details_line(line: str) -> dict[str, str]:
    parts = [part.strip() for part in line.split(DETAIL_SEPARATOR)]
    details: dict[str, str] = {}
    if len(parts) >= 4:
        details["language"], details["format"], details["size"], details["year"] = (
            parts[0],
            parts[1],
            parts[2],
            parts[-1],
        )
    elif len(parts) == 3:
        details["language"], details["format"], details["size"] = parts
    return details


def parse_results(html_text: str, limit: int = 20) -> list[dict[str, Any]]:
    """Pure parser: anchors href="/md5/<32hex>", inner text is the title, following
    text nodes supply the author and the "language · FORMAT · size · year" line.

    Dedupes by md5 and never raises on malformed input.
    """
    if not isinstance(html_text, str) or limit <= 0:
        return []
    try:
        parser = _CardParser()
        parser.feed(html_text)
        parser.close()
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    seen_md5: set[str] = set()
    anchors = parser.anchor_events
    for position, (href, inner_text, _start, end) in enumerate(anchors):
        match = MD5_HREF.match((href or "").strip())
        if not match:
            continue
        md5 = match.group(1).lower()
        if md5 in seen_md5:
            continue
        stop = anchors[position + 1][2] if position + 1 < len(anchors) else len(parser.text_nodes)
        following = parser.text_nodes[end:stop]
        author = ""
        details_text = ""
        for candidate in following:
            if DETAIL_SEPARATOR in candidate:
                details_text = candidate
                break
            if not author:
                author = candidate
        details = parse_details_line(details_text) if details_text else {}
        results.append(
            {
                "md5": md5,
                "title": inner_text or md5,
                "author": author,
                "url": href,
                **details,
            }
        )
        seen_md5.add(md5)
        if len(results) >= limit:
            break
    return results


def _looks_like_challenge(status_code: int, body: str) -> bool:
    if status_code in {401, 403, 429}:
        return True
    lowered = body.lower()
    return any(mark in lowered for mark in CHALLENGE_MARKS)


class AnnaArchive:
    def __init__(
        self,
        mirror: str | None = None,
        key: str | None = None,
        store_dir: Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.mirror = (mirror or os.environ.get("ANNAS_MIRROR") or DEFAULT_MIRROR).rstrip("/")
        self.key = key if key is not None else os.environ.get("ANNAS_KEY", "")
        self.store_dir = Path(store_dir or os.environ.get("ANNAS_STORE") or default_store_dir())
        self.cookies = CookieJar()
        self.signed_in = False
        self.challenged = False
        self._transport = transport
        self._cache: OrderedDict[tuple[str, int], tuple[float, dict[str, Any]]] = OrderedDict()
        self._pins: list[dict[str, Any]] = []

    def pin_result(self, item: dict[str, Any]) -> dict[str, Any]:
        pin = {"id": f"annas:{str(item.get('md5') or '') or len(self._pins)}", "item": item}
        self._pins.append(pin)
        return pin

    def pinned(self) -> list[dict[str, Any]]:
        return list(self._pins)

    def unpin(self, pin_id: str) -> dict[str, Any]:
        before = len(self._pins)
        self._pins[:] = [pin for pin in self._pins if pin["id"] != pin_id]
        return {"removed": len(self._pins) < before, "id": pin_id}

    def client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.mirror,
            transport=self._transport,
            cookies=self.cookies,
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": "ResearchHub-annas-tier/0.1"},
        )

    def sign_in(self, client: httpx.Client) -> None:
        response = client.post("/account/", data={"key": self.key})
        body = response.text
        if response.status_code in {200, 204} and not _looks_like_challenge(200, body):
            self.signed_in = True
            self.challenged = False
        else:
            self.signed_in = False
            self.challenged = True
            raise ChallengeEncountered("mirror sign-in rejected or challenged")

    @staticmethod
    def _cache_get(cache, key) -> Any | None:
        entry = cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= time.monotonic():
            del cache[key]
            return None
        cache.move_to_end(key)
        return value

    @staticmethod
    def _cache_put(cache, key, value, ttl=CACHE_TTL, maxsize=CACHE_MAX_ENTRIES):
        cache[key] = (time.monotonic() + ttl, value)
        cache.move_to_end(key)
        while len(cache) > maxsize:
            cache.popitem(last=False)

    def search(self, query: str, limit: int = 20, strict: bool = False) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            return {"results": [], "note": "empty query"}
        key = (query.strip(), int(limit))
        cached = self._cache_get(self._cache, key)
        if cached is not None:
            return cached
        with self.client() as client:
            if not self.signed_in:
                try:
                    self.sign_in(client)
                except (ChallengeEncountered, httpx.HTTPError) as error:
                    self.challenged = True
                    if strict and isinstance(error, ChallengeEncountered):
                        raise
                    return {"results": [], "note": "challenge"}
            try:
                response = client.get("/search", params={"q": query})
            except httpx.HTTPError as error:
                return {"results": [], "note": f"search failed: {error.__class__.__name__}"}
            if _looks_like_challenge(response.status_code, response.text):
                self.challenged = True
                self.signed_in = False
                if strict:
                    raise ChallengeEncountered("mirror returned a challenge response")
                return {"results": [], "note": "challenge"}
            parsed = parse_results(response.text, limit)
        results = []
        for item in parsed:
            item = dict(item)
            item["url"] = urljoin_mirror(self.mirror, item["url"])
            results.append(item)
        payload = {"results": results, "note": ""}
        self._cache_put(self._cache, key, payload)
        return payload

    def download(self, md5: str) -> dict[str, Any]:
        md5 = (md5 or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{32}", md5):
            return {"saved": False, "note": "invalid md5"}
        self.store_dir.mkdir(parents=True, exist_ok=True)
        with self.client() as client:
            if not self.signed_in:
                try:
                    self.sign_in(client)
                except (ChallengeEncountered, httpx.HTTPError):
                    self.challenged = True
                    return {"saved": False, "note": "challenge"}
            try:
                response = client.get("/dyn/api/fast_download.json", params={"md5": md5})
            except httpx.HTTPError as error:
                return {"saved": False, "note": f"download failed: {error.__class__.__name__}"}
            if _looks_like_challenge(response.status_code, response.text):
                self.challenged = True
                self.signed_in = False
                return {"saved": False, "note": "challenge"}
            try:
                payload = response.json()
            except (json.JSONDecodeError, ValueError):
                return {"saved": False, "note": "download metadata was not JSON"}
            target_url = payload.get("download_url") if isinstance(payload, dict) else None
            if not target_url:
                return {"saved": False, "note": "no download_url in response"}
            try:
                with client.stream("GET", target_url) as stream:
                    stream.raise_for_status()
                    disposition = stream.headers.get("content-disposition", "")
                    name_match = re.search(r'filename="?([^";]+)"?', disposition)
                    suffix = Path(name_match.group(1)).suffix if name_match else ".bin"
                    destination = self.store_dir / f"{md5}{suffix}"
                    written = 0
                    truncated = False
                    with destination.open("wb") as handle:
                        for chunk in stream.iter_bytes():
                            room = DOWNLOAD_CAP - written
                            if room <= 0:
                                truncated = True
                                break
                            handle.write(chunk[:room])
                            written += min(len(chunk), room)
                            if len(chunk) > room:
                                truncated = True
                                break
            except httpx.HTTPError as error:
                return {"saved": False, "note": f"download failed: {error.__class__.__name__}"}
        note = "Truncated at 250 MiB cap." if truncated else ""
        return {
            "saved": True,
            "md5": md5,
            "path": str(destination),
            "bytes": written,
            "note": note,
        }


def urljoin_mirror(mirror: str, href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return mirror.rstrip("/") + (href if href.startswith("/") else "/" + href)
