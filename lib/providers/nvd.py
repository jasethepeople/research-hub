"""NVD tier: keyword search over the National Vulnerability Database."""

from typing import Any

from lib.providers.http import get

API = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def search(query: str, limit: int = 20) -> dict[str, Any]:
    response = get(
        API,
        params={"keywordSearch": query.strip(), "resultsPerPage": min(max(limit, 1), 50)},
        timeout=40.0,
    )
    payload = response.json()
    results = []
    for entry in payload.get("vulnerabilities", [])[: max(limit, 1)]:
        cve = entry.get("cve", {})
        cve_id = str(cve.get("id", "")).strip()
        if not cve_id:
            continue
        descriptions = cve.get("descriptions", [])
        description = next((d.get("value", "") for d in descriptions if d.get("lang") == "en"), "")
        description = " ".join(description.split())[:400]
        severity, score = "", ""
        metrics = cve.get("metrics", {})
        for metric_key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            if metric_key in metrics and metrics[metric_key]:
                data = metrics[metric_key][0].get("cvssData", {})
                severity = str(data.get("baseSeverity") or metrics[metric_key][0].get("baseSeverity") or "")
                score = str(data.get("baseScore") or "")
                break
        references = [ref.get("url", "") for ref in cve.get("references", []) if ref.get("url")]
        link = references[0] if references else f"https://nvd.nist.gov/vuln/detail/{cve_id}"
        results.append(
            {
                "title": f"{cve_id}: {description[:160]}" if description else cve_id,
                "url": link,
                "author": f"{severity} {score}".strip(),
                "published": str(cve.get("published") or "")[:10],
                "source": "NVD",
                "id": cve_id,
            }
        )
    return {"results": results, "note": ""}