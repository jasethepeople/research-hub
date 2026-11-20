"""osm tier: OpenStreetMap name search via Nominatim (places, peaks, rivers, features)."""
import lib.providers.http as http

API = "https://nominatim.openstreetmap.org/search"


def search(query: str, limit: int = 20) -> dict:
    response = http.get(
        API,
        params={
            "q": query.strip(),
            "format": "jsonv2",
            "limit": str(min(max(limit, 1), 50)),
            "addressdetails": "0",
        },
        timeout=45.0,
    )
    rows = response.json()
    results = []
    for row in rows:
        results.append(
            {
                "title": str(row.get("name") or row.get("display_name", "")),
                "author": str(row.get("type") or row.get("category") or "place"),
                "url": f"https://www.openstreetmap.org/{row.get('osm_type', 'node')}/{row.get('osm_id', '')}",
                "snippet": str(row.get("display_name", "")),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "tier": "osm",
            }
        )
    return {"results": results, "note": "OpenStreetMap places & features (Nominatim)"}
