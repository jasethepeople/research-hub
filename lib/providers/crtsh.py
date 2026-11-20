"""crtsh tier: certificate-transparency search via crt.sh (domains, subdomains, identities)."""
import lib.providers.http as http

API = "https://crt.sh/"


def search(query: str, limit: int = 20) -> dict:
    needle = query.strip()
    if not needle or needle.startswith("*"):
        return {"results": [], "note": "enter a domain or identity (e.g. example.com)"}
    response = http.get(API, params={"q": needle, "output": "json", "exclude": "expired"}, timeout=90.0)
    try:
        rows = response.json()
    except ValueError:
        return {"results": [], "note": "crt.sh returned non-JSON (often under load, retry)"}
    results, seen = [], set()
    for row in rows:
        name_value = str(row.get("common_name") or row.get("name_value") or "").split("\n")[0]
        key = (name_value, str(row.get("issuer_name", "")))
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "title": name_value,
                "author": str(row.get("issuer_name", "")).replace("O=", "").split(",")[0],
                "url": f"https://crt.sh/?id={row.get('id')}",
                "year": str(row.get("not_before") or "")[:10],
                "tier": "crtsh",
            }
        )
        if len(results) >= limit:
            break
    return {"results": results, "note": "certificate transparency (crt.sh)"}
