"""fdroid tier."""
import lib.providers.http as http

INDEX = "https://f-droid.org/repo/index-v2.json"

_cache: dict[str, object] = {}

def search(query: str, limit: int = 20) -> dict[str, object]:
    if not _cache.get("apps"):
        response = http.get(INDEX, timeout=120.0)
        packages = response.json().get("packages", {})
        apps = []
        for package_id, meta in packages.items():
            name_info = (meta.get("metadata") or {}).get("name") or {}
            name = name_info.get("en-US") or package_id
            desc = ((meta.get("metadata") or {}).get("description") or {}).get("en-US") or ""
            apps.append({"id": package_id, "name": name, "desc": desc})
        _cache["apps"] = apps
    words = [w.lower() for w in query.split() if len(w) > 1]
    results = []
    for app in _cache["apps"]:
        haystack = f"{app['name']} {app['id']} {app['desc']}".lower()
        if all(w in haystack for w in words):
            results.append({
                "title": f"{app['name']} (F-Droid)",
                "author": "",
                "url": f"https://f-droid.org/packages/{app['id']}/",
                "snippet": app["desc"][:300],
            })
    return {"results": results[:limit], "note": ""}

