"""Europe PMC Open Access literature search."""

from lib.providers._shadow import API_UA, cache, format_results, get_json

API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MIRRORS = ("https://www.ebi.ac.uk",)
HEADERS = {"User-Agent": API_UA}


def parse_response(payload: dict, limit: int = 20) -> dict:
    if isinstance(payload, dict) and payload.get("kind") == "transport-observation":
        note = str(payload.get("note") or "mirror-dead")
        if note in {"challenge", "cloudflare-403", "mirror-dead", "needs-key", "parse-drift"}:
            return {"results": [], "note": note}
        raise ValueError("invalid Europe PMC transport observation")
    result_list = payload.get("resultList") if isinstance(payload, dict) else None
    records = result_list.get("result") if isinstance(result_list, dict) else None
    if not isinstance(records, list):
        raise ValueError("Europe PMC response schema changed")
    results = []
    for record in records:
        if not isinstance(record, dict):
            continue
        title = " ".join(str(record.get("title") or "").split())
        source = str(record.get("source") or "MED").strip()
        identifier = str(record.get("id") or "").strip()
        doi = str(record.get("doi") or "").strip()
        url = (
            f"https://europepmc.org/article/{source}/{identifier}"
            if identifier
            else f"https://doi.org/{doi}" if doi else ""
        )
        if not title or not url:
            continue
        results.append(
            {
                "title": title,
                "author": " ".join(str(record.get("authorString") or "").split()),
                "url": url,
                "doi": doi,
                "pmcid": str(record.get("pmcid") or ""),
                "year": str(record.get("pubYear") or ""),
                "is_open_access": str(record.get("isOpenAccess") or "").upper() == "Y",
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict:
    payload = get_json(
        API,
        params={
            "query": f"({query}) AND OPEN_ACCESS:Y",
            "pageSize": limit,
            "format": "json",
            "resultType": "core",
        },
        headers=HEADERS,
        mirrors=MIRRORS,
    )
    return parse_response(payload, limit)
