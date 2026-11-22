from __future__ import annotations

import copy
import html
import json
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from functools import wraps
from typing import Any, TypeVar
from urllib.parse import urljoin, urlsplit

import httpx

TIMEOUT_SECONDS = 8.0
RETRIES = 2
MAX_IN_FLIGHT = 3
CACHE_TTL_SECONDS = 900.0
CACHE_MAX_ENTRIES = 200
MIRROR_COOLDOWN_SECONDS = 300.0
API_UA = "ResearchHubTiers/0.1 (+https://github.com/jasethepeople/research-hub-tiers)"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
DEFAULT_HEADERS = {"Accept": "application/json, text/html, application/xml;q=0.9, */*;q=0.8", "User-Agent": API_UA}
FAILURE_NOTES = {"challenge", "cloudflare-403", "mirror-dead", "needs-key", "parse-drift"}

T = TypeVar("T")
_semaphore = threading.BoundedSemaphore(MAX_IN_FLIGHT)
_cache_lock = threading.RLock()
_cache: OrderedDict[tuple[str, str, int], tuple[float, dict[str, Any]]] = OrderedDict()
_mirror_lock = threading.RLock()
_last_good: dict[tuple[str, ...], str] = {}
_dead_until: dict[str, float] = {}
_request_state = threading.local()
_rate_lock = threading.Lock()
_rate_deadlines: dict[str, float] = {}


class ProviderFailure(Exception):
    note = "mirror-dead"


class Challenge(ProviderFailure):
    note = "challenge"


class Cloudflare403(Challenge):
    note = "cloudflare-403"


class MirrorDead(ProviderFailure):
    note = "mirror-dead"


class NeedsKey(ProviderFailure):
    note = "needs-key"


class ParseDrift(ProviderFailure):
    note = "parse-drift"


class HttpFailure(ProviderFailure):
    note = "parse-drift"

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


def clean(text: Any) -> str:
    return " ".join(html.unescape(str(text or "")).split())


def throttle(key: str, interval_seconds: float) -> None:
    normalized_key = clean(key).casefold()
    interval = max(0.0, float(interval_seconds))
    if not normalized_key or interval <= 0:
        return
    with _rate_lock:
        now = time.monotonic()
        delay = _rate_deadlines.get(normalized_key, 0.0) - now
        if delay > 0:
            time.sleep(delay)
        now = time.monotonic()
        _rate_deadlines[normalized_key] = now + interval
        if len(_rate_deadlines) > CACHE_MAX_ENTRIES:
            for source, deadline in tuple(_rate_deadlines.items()):
                if deadline <= now:
                    del _rate_deadlines[source]
            if len(_rate_deadlines) > CACHE_MAX_ENTRIES:
                _rate_deadlines.pop(next(iter(_rate_deadlines)))


def absolutize(base: str, href: str) -> str:
    return urljoin(base, str(href or "").strip())


def format_results(results: Sequence[Mapping[str, Any]], limit: int = 20, note: str = "") -> dict[str, Any]:
    bounded_limit = clamp_limit(limit)
    unique: list[dict[str, Any]] = []
    seen = set()
    for item in results:
        title = clean(item.get("title"))
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            continue
        normalized = {**item, "title": title, "url": url}
        key = _result_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    result_note = clean(note) or ("no-results" if not unique else "")
    return {"results": unique[:bounded_limit], "note": result_note}


def normalize_query(query: str) -> str:
    return clean(query)


def clamp_limit(limit: Any, maximum: int = 50) -> int:
    try:
        requested = int(limit)
    except (TypeError, ValueError, OverflowError):
        requested = 20
    return max(1, min(requested, maximum))


def credential_for(slug: str) -> str | None:
    env_name = f"HUB_TIER_{slug.upper().replace('-', '_')}__KEY"
    return os.environ.get(env_name) or None


def last_http_status() -> int | None:
    return getattr(_request_state, "status", None)


def clear_last_http_status() -> None:
    if hasattr(_request_state, "status"):
        del _request_state.status


def note_for_error(error: BaseException) -> str:
    if isinstance(error, ProviderFailure):
        return error.note
    if isinstance(error, httpx.RequestError):
        return "mirror-dead"
    return "parse-drift"


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _mirror_candidates(url: str, mirrors: Sequence[str] | None) -> tuple[str, ...]:
    if not mirrors:
        return (url,)
    bases = tuple(dict.fromkeys(str(base).rstrip("/") for base in mirrors if base))
    parts = urlsplit(url)
    path = parts.path.lstrip("/")
    if parts.query:
        path = f"{path}?{parts.query}"
    now = time.monotonic()
    with _mirror_lock:
        available = [base for base in bases if _dead_until.get(base, 0.0) <= now]
        last = _last_good.get(bases)
    if last in available:
        available.remove(last)
        available.insert(0, last)
    return tuple(urljoin(f"{base}/", path) for base in available)


def _mark_good(bases: tuple[str, ...], url: str) -> None:
    origin = _origin(url)
    with _mirror_lock:
        if bases:
            _last_good[bases] = origin
        _dead_until.pop(origin, None)


def _mark_dead(url: str) -> None:
    with _mirror_lock:
        _dead_until[_origin(url)] = time.monotonic() + MIRROR_COOLDOWN_SECONDS


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    body = response.text[:500].lower()
    if status == 401:
        raise NeedsKey("authentication required")
    if status == 403:
        if "cf-ray" in response.headers or "cloudflare" in body or "attention required" in body:
            raise Cloudflare403("Cloudflare denied the request")
        raise Challenge("access challenge")
    if status == 429:
        raise Challenge("rate limited")
    if status in (404, 410) or status >= 500:
        raise MirrorDead(f"HTTP {status}")
    raise HttpFailure(status)


def _request(
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    mirrors: Sequence[str] | None = None,
    method: str = "GET",
    allow_status_errors: bool = False,
) -> httpx.Response:
    bases = tuple(dict.fromkeys(str(base).rstrip("/") for base in (mirrors or ()) if base))
    candidates = _mirror_candidates(url, bases)
    if not candidates:
        raise MirrorDead("all mirrors are cooling down")
    last_error: BaseException | None = None
    merged_headers = {**DEFAULT_HEADERS, **dict(headers or {})}
    for candidate in candidates:
        for attempt in range(RETRIES + 1):
            try:
                with _semaphore:
                    response = httpx.request(
                        method,
                        candidate,
                        params=params,
                        headers=merged_headers,
                        timeout=TIMEOUT_SECONDS,
                        follow_redirects=True,
                    )
                _request_state.status = response.status_code
                if response.status_code == 429 or 500 <= response.status_code <= 599:
                    if attempt < RETRIES:
                        time.sleep(0.2 * (2**attempt))
                        continue
                if allow_status_errors:
                    if 200 <= response.status_code < 400:
                        _mark_good(bases, candidate)
                    elif response.status_code >= 500:
                        _mark_dead(candidate)
                    return response
                try:
                    _raise_for_status(response)
                except (Cloudflare403, MirrorDead) as error:
                    _mark_dead(candidate)
                    last_error = error
                    break
                except Challenge as error:
                    last_error = error
                    break
                _mark_good(bases, candidate)
                return response
            except (NeedsKey, HttpFailure):
                raise
            except MirrorDead as error:
                _mark_dead(candidate)
                last_error = error
                break
            except httpx.RequestError as error:
                last_error = error
                if attempt < RETRIES:
                    time.sleep(0.2 * (2**attempt))
                    continue
                _mark_dead(candidate)
                break
    if last_error is not None:
        if isinstance(last_error, ProviderFailure):
            raise last_error
        raise MirrorDead(last_error.__class__.__name__) from last_error
    raise MirrorDead("no mirror returned a response")


def get_html(
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    mirrors: Sequence[str] | None = None,
) -> str:
    request_headers = {"User-Agent": BROWSER_UA, **dict(headers or {})}
    response = _request(url, params=params, headers=request_headers, mirrors=mirrors)
    body = response.text
    if not body.strip():
        raise ParseDrift("empty response body")
    return body


def get_json(
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    mirrors: Sequence[str] | None = None,
) -> Any:
    response = _request(url, params=params, headers=headers, mirrors=mirrors)
    if not response.content.strip():
        raise ParseDrift("empty response body")
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        raise ParseDrift("response is not valid JSON") from error


def get_raw_response(
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    mirrors: Sequence[str] | None = None,
) -> tuple[int, bytes]:
    response = _request(
        url,
        params=params,
        headers=headers,
        mirrors=mirrors,
        allow_status_errors=True,
    )
    return response.status_code, response.content


def _result_key(item: Mapping[str, Any]) -> str:
    url = str(item.get("url") or "").strip().casefold().rstrip("/")
    return f"url:{url}" if url else f"title:{clean(item.get('title')).casefold()}"


def cache(function: Callable[[str, int], dict[str, Any]]) -> Callable[[str, int], dict[str, Any]]:
    @wraps(function)
    def wrapped(query: str, limit: int = 20) -> dict[str, Any]:
        normalized = normalize_query(query)
        bounded_limit = clamp_limit(limit)
        if not normalized:
            return {"results": [], "note": "no-results"}
        key = (function.__module__, normalized.casefold(), bounded_limit)
        now = time.monotonic()
        with _cache_lock:
            cached = _cache.get(key)
            if cached and now - cached[0] < CACHE_TTL_SECONDS:
                _cache.move_to_end(key)
                return copy.deepcopy(cached[1])
            _cache.pop(key, None)
        try:
            result = function(normalized, bounded_limit)
            if not isinstance(result, dict) or not isinstance(result.get("results"), list):
                raise ParseDrift("provider returned an invalid result shape")
            items = [item for item in result["results"] if isinstance(item, dict)]
            response = format_results(items, bounded_limit, clean(result.get("note")))
        except Exception as error:
            return {"results": [], "note": note_for_error(error)}
        if response["note"] not in FAILURE_NOTES:
            with _cache_lock:
                _cache[key] = (now, copy.deepcopy(response))
                _cache.move_to_end(key)
                while len(_cache) > CACHE_MAX_ENTRIES:
                    _cache.popitem(last=False)
        return response

    return wrapped


def probe_url(url: str, *, mirrors: Sequence[str] | None = None) -> tuple[int | None, str]:
    clear_last_http_status()
    try:
        _request(url, mirrors=mirrors, method="HEAD")
    except HttpFailure as error:
        if error.status_code not in (405, 501):
            return last_http_status(), note_for_error(error)
        try:
            _request(url, mirrors=mirrors, method="GET")
        except Exception as get_error:
            return last_http_status(), note_for_error(get_error)
    except Exception as error:
        return last_http_status(), note_for_error(error)
    return last_http_status(), ""


def probe(url: str, *, mirrors: Sequence[str] | None = None) -> int | None:
    return probe_url(url, mirrors=mirrors)[0]


__all__ = [
    "API_UA",
    "BROWSER_UA",
    "CACHE_MAX_ENTRIES",
    "CACHE_TTL_SECONDS",
    "Cloudflare403",
    "Challenge",
    "HttpFailure",
    "MAX_IN_FLIGHT",
    "MirrorDead",
    "NeedsKey",
    "ParseDrift",
    "absolutize",
    "cache",
    "clean",
    "clamp_limit",
    "clear_last_http_status",
    "credential_for",
    "format_results",
    "get_html",
    "get_json",
    "get_raw_response",
    "last_http_status",
    "note_for_error",
    "normalize_query",
    "probe",
    "probe_url",
    "throttle",
]
