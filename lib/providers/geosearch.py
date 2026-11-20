"""geosearch tier: worldwide place search via the Esri ArcGIS World Geocoder."""
import lib.providers.http as http

API = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"


def search(query: str, limit: int = 20) -> dict:
    needle = query.replace('"', "")
    if not needle:
        return {"results": [], "note": "empty query"}
    response = http.get(
        API,
        params={
            "singleLine": needle,
            "outFields": "PlaceName,Region,Country,Type",
            "maxLocations": str(min(max(limit, 1), 50)),
            "f": "json",
        },
        timeout=30.0,
    )
    results = []
    for cand in response.json().get("candidates", [])[:limit]:
        attrs = cand.get("attributes", {})
        results.append(
            {
                "title": str(attrs.get("PlaceName") or cand.get("address") or ""),
                "author": str(attrs.get("Type") or "place"),
                "url": f"https://www.openstreetmap.org/#map=12/{cand.get('location', {}).get('y')}/{cand.get('location', {}).get('x')}",
                "snippet": ", ".join(filter(None, [attrs.get("PlaceName"), attrs.get("Region"), attrs.get("Country")])),
                "lat": cand.get("location", {}).get("y"),
                "lon": cand.get("location", {}).get("x"),
                "tier": "geosearch",
            }
        )
    return {"results": results, "note": "Esri world geocoder"}
