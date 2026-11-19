"""OSV tier: look up vulnerabilities by ID (CVE, GHSA, PYSEC, OSV, MAL...)."""

import re
from typing import Any

from lib.providers.http import get

API = "https://api.osv.dev/v1/vulns"
ID_PATTERN = re.compile(r"^(CVE-\d{4}-\d{4,}|GHSA-[A-Za-z0-9-]{6,}|OSV-[A-Za-z0-9-]+|PYSEC-\d{4}-\d+|MAL-\w{4,})$",
    re.IGNORECASE)

def search(query: str, limit: int = 20) -> dict[str, Any]:
    token = query.strip().upper()
    if not ID_PATTERN.match(token):
        return {"results": [], "note": "enter a vulnerability ID (CVE-..., GHSA-..., PYSEC-...)"}
    try:
        response = get(f"{API}/{token}", timeout=20.0)
    except Exception:
        return {"results": [], "note": f"{token} not found in OSV"}
    vuln = response.json()
    aliases = [str(alias) for alias in vuln.get("aliases", [])]
    summary = " ".join(str(vuln.get("summary") or vuln.get("details") or "").split())[:400]
    severity = ""
    sev_entries = vuln.get("severity", [])
    if sev_entries and sev_entries[0].get("score"):
        severity = " ".join(str(sev_entries[0]["score"]).split())[:60]
    references = [ref.get("url", "") for ref in vuln.get("references", []) if ref.get("url")]
    link = next((u for u in references if "advisory" in u or "github" in u), f"https://osv.dev/vulnerability/{token}")
    affected = []
    for entry in vuln.get("affected", [])[:6]:
        package = (entry.get("package") or {}).get("name", "")
        if package:
            affected.append(package)
    return {
        "results": [
            {
                "title": f"{token}: {summary[:160]}" if summary else token,
                "url": link,
                "author": severity,
                "published": str(vuln.get("published") or "")[:10],
                "source": " · ".join(part for part in ("OSV", ", ".join(aliases[:3]), ", ".join(affected[:3])) if part),
                "id": token,
            }
        ],
        "note": "",
    }