"""metasploit tier."""
import time

import httpx

RAW = "https://raw.githubusercontent.com/rapid7/metasploit-framework/master/db/modules_metadata_base.json"

_cache: dict[str, object] = {"modules": None, "ts": 0.0}

def search(query: str, limit: int = 20) -> dict[str, object]:
    q = query.strip().lower()
    now = time.time()
    if _cache["modules"] is None or now - float(_cache["ts"]) > 6 * 3600:
        response = httpx.get(RAW, timeout=60.0, follow_redirects=True)
        response.raise_for_status()
        _cache["modules"] = response.json()
        _cache["ts"] = now
    modules = _cache["modules"]
    results = []
    for key, m in modules.items():
        haystack = f"{m.get('name', '')} {m.get('description', '')} {m.get('fullname', key)}".lower()
        if q in haystack:
            refs = m.get("references") or []
            ref = ""
            for r in refs or []:
                if isinstance(r, str):
                    ref = r
                elif isinstance(r, dict):
                    ref = r.get("url") or r.get("href") or ""
                if ref:
                    break
            results.append({
                "title": m.get("name") or key,
                "author": ", ".join(m.get("authors", [])[:3]) if isinstance(m.get("authors"),
                    list) else (m.get("autho rs") or ""),
                "url": ref or f"https://www.rapid7.com/db/modules/{m.get('fullname', key)}/",
                "snippet": (m.get("description") or "")[:300],
            })
    return {"results": results[:limit], "note": ""}

