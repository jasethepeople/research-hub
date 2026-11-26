from __future__ import annotations

import threading
import time
from typing import Any

from lib.providers._shadow import API_UA, ParseDrift, cache, format_results, get_json

SEARCH_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
SUMMARY_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
MIRRORS = ("https://eutils.ncbi.nlm.nih.gov",)
HEADERS = {"User-Agent": API_UA}
MIN_REQUEST_INTERVAL = 0.34
_request_lock = threading.Lock()
_last_request_at = 0.0


def _get_json(url: str, params: dict[str, Any]) -> Any:
    global _last_request_at
    with _request_lock:
        delay = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
        if delay > 0:
            time.sleep(delay)
        try:
            return get_json(url, params=params, headers=HEADERS, mirrors=MIRRORS)
        finally:
            _last_request_at = time.monotonic()


def _fetch_payload(query: str, limit: int) -> dict[str, Any]:
    search = _get_json(
        SEARCH_API,
        {
            "db": "pubmed",
            "term": query,
            "retmax": limit,
            "retmode": "json",
            "sort": "relevance",
            "tool": "research-hub-tiers",
        },
    )
    search_result = search.get("esearchresult") if isinstance(search, dict) else None
    identifiers = search_result.get("idlist") if isinstance(search_result, dict) else None
    if not isinstance(identifiers, list):
        raise ParseDrift("PubMed ESearch response schema changed")
    identifiers = [str(identifier) for identifier in identifiers[:limit] if str(identifier).isdigit()]
    if not identifiers:
        return {"search": search, "summary": {"result": {"uids": []}}}
    summary = _get_json(
        SUMMARY_API,
        {
            "db": "pubmed",
            "id": ",".join(identifiers),
            "retmode": "json",
            "tool": "research-hub-tiers",
        },
    )
    return {"search": search, "summary": summary}


def parse_response(payload: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    search = payload.get("search") if isinstance(payload, dict) else None
    search_result = search.get("esearchresult") if isinstance(search, dict) else None
    identifiers = search_result.get("idlist") if isinstance(search_result, dict) else None
    summary = payload.get("summary") if isinstance(payload, dict) else None
    records = summary.get("result") if isinstance(summary, dict) else None
    if not isinstance(identifiers, list) or not isinstance(records, dict):
        raise ParseDrift("PubMed response schema changed")
    if not identifiers:
        return format_results([], limit)
    uids = records.get("uids")
    if not isinstance(uids, list):
        raise ParseDrift("PubMed ESummary response schema changed")
    results = []
    for identifier in identifiers[:limit]:
        pmid = str(identifier)
        if not pmid.isdigit():
            continue
        record = records.get(pmid)
        if not isinstance(record, dict):
            continue
        title = " ".join(str(record.get("title") or "").split())
        if not title:
            continue
        authors = record.get("authors") or []
        author_names = [
            " ".join(str(author.get("name") or "").split())
            for author in authors
            if isinstance(author, dict)
        ]
        author = ", ".join(name for name in author_names if name) or str(
            record.get("sortfirstauthor") or ""
        )
        results.append(
            {
                "pmid": pmid,
                "title": title,
                "author": " ".join(author.split()),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "journal": " ".join(str(record.get("fulljournalname") or record.get("source") or "").split()),
                "year": " ".join(str(record.get("pubdate") or "").split()),
                "doi": " ".join(str(record.get("elocationid") or "").split()),
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict[str, Any]:
    return parse_response(_fetch_payload(query, limit), limit)


__all__ = ["parse_response", "search"]
