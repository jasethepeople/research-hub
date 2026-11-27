"""The Metropolitan Museum of Art Open Access Collection API."""

from lib.providers._shadow import cache, format_results, get_json

SEARCH_API = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
OBJECT_API = "https://collectionapi.metmuseum.org/public/collection/v1/objects"
MIRRORS = ("https://collectionapi.metmuseum.org",)


def parse_response(payload: dict, limit: int = 20) -> dict:
    search_payload = payload.get("search") if isinstance(payload, dict) else None
    objects = payload.get("objects") if isinstance(payload, dict) else None
    if (
        not isinstance(search_payload, dict)
        or "objectIDs" not in search_payload
        or not isinstance(objects, list)
    ):
        raise ValueError("Met collection response schema changed")
    results = []
    for item in objects[:limit]:
        if not isinstance(item, dict) or not item.get("isPublicDomain"):
            continue
        title = " ".join(str(item.get("title") or "").split())
        url = str(item.get("objectURL") or "").strip()
        if not title or not url:
            continue
        results.append(
            {
                "title": title,
                "author": " ".join(str(item.get("artistDisplayName") or "").split()),
                "url": url,
                "year": str(item.get("objectDate") or ""),
                "department": str(item.get("department") or ""),
                "is_public_domain": True,
                "image": str(item.get("primaryImageSmall") or ""),
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict:
    search_payload = get_json(
        SEARCH_API,
        params={"q": query, "hasImages": "true", "isPublicDomain": "true", "limit": min(limit, 10)},
        mirrors=MIRRORS,
    )
    if not isinstance(search_payload, dict) or "objectIDs" not in search_payload:
        raise ValueError("Met search response schema changed")
    object_ids = search_payload["objectIDs"]
    if object_ids is None:
        return {"results": [], "note": ""}
    if not isinstance(object_ids, list):
        raise ValueError("Met objectIDs field is not a list")
    objects = []
    for object_id in object_ids[: min(limit, 10)]:
        item = get_json(f"{OBJECT_API}/{int(object_id)}", mirrors=MIRRORS)
        if isinstance(item, dict):
            objects.append(item)
    return parse_response({"search": search_payload, "objects": objects}, limit)
