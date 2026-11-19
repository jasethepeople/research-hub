"""stackexchange tier."""
import html as html_mod

import lib.providers.http as http

API = "https://api.stackexchange.com/2.3/search/excerpts"

def search(query: str, limit: int = 20) -> dict[str, object]:
    response = http.get(
        API,
        params={
            "order": "desc",
            "sort": "relevance",
            "q": query.strip(),
            "site": "stackoverflow",
            "pagesize": min(max(limit, 1), 50),
        },
        timeout=30.0,
    )
    results = []
    for item in response.json().get("items", []):
        title = html_mod.unescape(item.get("title") or "")
        qid = item.get("question_id")
        url = f"https://stackoverflow.com/q/{qid}"
        if not qid:
            url = "https://stackoverflow.com/search?q=" + query.strip().replace(" ", "+")
        results.append({
            "title": title or "Stack Overflow result",
            "author": "",
            "url": url,
            "snippet": html_mod.unescape(item.get("excerpt") or "")[:300],
        })
    return {"results": results, "note": ""}

