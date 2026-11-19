"""Shared HTTP helper: polite Crossref user-agent, redirect following, 429 retry."""

import httpx

BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)
POLITE_UA = "ResearchHub/0.1 (mailto:research-hub@users.noreply.github.com)"


def get(url: str, *, params: dict | None = None, pairs: list | None = None,
        headers: dict | None = None, timeout: float = 25.0, retries: int = 2, polite: bool = True) -> httpx.Response:
    if pairs:
        base = str(httpx.QueryParams(params or {}))
        extra = "&".join(
            f"{httpx.QueryParams({k: ''})[k]}={httpx.QueryParams({v: ''})[v]}" for k, v in pairs
        )
        url = f"{url}?{base}&{extra}" if base else f"{url}?{extra}"
        params = None
    merged = {"User-Agent": POLITE_UA if polite else BROWSER_UA}
    if headers:
        merged.update(headers)
    attempt = 0
    while True:
        attempt += 1
        response = httpx.get(
            url, params=params, headers=merged, timeout=timeout, follow_redirects=True
        )
        if response.status_code == 429 and attempt <= retries:
            import time
            time.sleep(min(2.0 * attempt, 5.0))
            continue
        response.raise_for_status()
        return response
