"""courtlistener tier: CourtListener free-jurisdiction case law & opinions.

Full-text search of US federal and state case law via the CourtListener API
(free, community-run). Uses COURTLISTENER_TOKEN from the environment when
present (recommended, higher rate limits); works tokenless with lower limits.
"""
import os

import httpx

API = "https://www.courtlistener.com/api/rest/v4/search/"


def search(query: str, limit: int = 25) -> dict:
    headers = {"User-Agent": "research-hub (contact: hub user)", "Accept": "application/json"}
    token = os.environ.get("COURTLISTENER_TOKEN", "")
    if token:
        headers["Authorization"] = f"Token {token}"
    try:
        response = httpx.get(
            API,
            params={"q": query, "type": "o", "order_by": "score desc", "page_size": min(limit, 20)},
            headers=headers,
            timeout=30.0,
        )
    except Exception as error:
        return {"results": [], "note": f"courtlistener unreachable: {type(error).__name__}"}
    if response.status_code == 401:
        return {"results": [], "note": "courtlistener rejected token — set COURTLISTENER_TOKEN (free token at courtlistener.com)"}
    if response.status_code == 429:
        return {"results": [], "note": "courtlistener rate-limited; a free COURTLISTENER_TOKEN raises the limits"}
    if response.status_code != 200:
        return {"results": [], "note": f"courtlistener HTTP {response.status_code}"}
    results = []
    for item in response.json().get("results", [])[:limit]:
        cites = ", ".join(item.get("citation", []) or [])
        results.append(
            {
                "title": str(item.get("caseName") or "(untitled case)"),
                "author": str(item.get("court") or ""),
                "url": f"https://www.courtlistener.com{item.get('absolute_url', '')}",
                "tier": "courtlistener",
                "snippet": (
                    cites + " — " if cites else ""
                ) + str(item.get("snippet") or "")[:250],
            }
        )
    note = "" if token else "no token set — free token at courtlistener.com raises limits (COURTLISTENER_TOKEN)"
    return {"results": results, "note": note}