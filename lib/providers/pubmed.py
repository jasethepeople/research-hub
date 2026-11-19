"""pubmed tier."""
import lib.providers.http as http

SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
SUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

def search(query: str, limit: int = 20) -> dict[str, object]:
    params = {"db": "pubmed", "term": query.strip(), "retmax": min(max(limit, 1), 50), "retmode": "json",
        "sort": "rel evance"}
    response = http.get(SEARCH, params=params, timeout=30.0)
    ids = response.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return {"results": [], "note": ""}
    response = http.get(SUMMARY, params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"}, timeout=30.0)
    docs = response.json().get("result", {})
    results = []
    for pmid in ids:
        doc = docs.get(pmid)
        if not doc:
            continue
        results.append({
            "title": doc.get("title") or "Untitled",
            "author": doc.get("sortfirstauthor") or "",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "snippet": doc.get("pubdate") or "",
        })
    return {"results": results, "note": ""}

