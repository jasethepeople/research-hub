"""usgs_topo tier: USGS historical + current topographic maps (TNM products API)."""
import lib.providers.http as http

API = "https://tnmaccess.nationalmap.gov/api/v1/products"


def search(query: str, limit: int = 20) -> dict:
    needle = query.replace('"', "")
    response = http.get(
        API,
        params={"q": needle, "products": "Topo Maps Historical,Topo Maps", "max": str(min(max(limit, 1), 50))},
        timeout=45.0,
    )
    items = response.json().get("items", [])
    results = []
    for item in items:
        results.append(
            {
                "title": str(item.get("title") or item.get("sourceId") or "USGS map"),
                "author": "U.S. Geological Survey",
                "url": str(item.get("detailsUrl") or item.get("downloadURL") or ""),
                "year": str(item.get("startDate") or "")[:10],
                "snippet": str(item.get("size") or ""),
                "tier": "usgs_topo",
            }
        )
    return {"results": results, "note": "USGS topo maps (free scans + geopdf)"}
