"""cisa_kev tier."""
import lib.providers.http as http

API = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

_cache: dict[str, object] = {}

def search(query: str, limit: int = 20) -> dict[str, object]:
    q = query.strip().lower()
    if not _cache.get("vulns"):
        response = http.get(API, timeout=60.0)
        _cache["vulns"] = response.json().get("vulnerabilities", [])
    results = []
    for v in _cache["vulns"]:
        haystack = " ".join(
            str(v.get(k, "")) for k in ("cveID", "vendorProject", "product", "vulnerabilityName", "shortDescription")
        ).lower()
        if q in haystack:
            results.append({
                "title": v.get("vulnerabilityName") or v.get("cveID") or "KEV entry",
                "author": v.get("vendorProject") or "",
                "url": f"https://nvd.nist.gov/vuln/detail/{v.get('cveID', '')}",
                "snippet": (v.get("shortDescription") or "")[:300],
            })
    return {"results": results[:limit], "note": ""}

