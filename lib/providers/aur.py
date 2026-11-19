"""aur tier."""
import urllib.parse

import lib.providers.http as http

API = "https://aur.archlinux.org/rpc/v5/search"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(f"{API}/{urllib.parse.quote(query.strip())}", params={"by": "name-desc", "limit": min(max(limit,
    1), 50)}, timeout=30.0)
    results = []
    for p in response.json().get("results", []):
        results.append({
            "title": f"{p.get('Name')} (AUR)",
            "author": p.get("Maintainer") or "",
            "url": f"https://aur.archlinux.org/packages/{p.get('Name', '')}",
            "snippet": (p.get("Description") or "")[:300],
        })
    return {"results": results, "note": ""}

