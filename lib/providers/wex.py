"""wex tier: Cornell Legal Information Institute (Wex legal encyclopedia)."""
import urllib.parse

from lib.providers.http import get

WEX_UA = "Mozilla/5.0 (X11; Linux x86_64) research-hub-wex"


def search(query: str, limit: int = 20) -> dict:
    query = query.strip()
    if not query:
        raise ValueError("search must not be blank")
    results: list[dict] = []
    slug = urllib.parse.quote(query.lower().replace(" ", "_"))
    try:
        response = get(
            f"https://www.law.cornell.edu/wex/{slug}",
            headers={"User-Agent": WEX_UA},
            timeout=25.0,
        )
    except Exception:
        response = None
    if response is not None and response.status_code == 200 and "wex" in response.text.lower():
        import re

        title_match = re.search(r"<title>([^<]+)</title>", response.text)
        results.append(
            {
                "title": (title_match.group(1) if title_match else query) + " — Wex (LII)",
                "author": "Cornell Legal Information Institute",
                "url": f"https://www.law.cornell.edu/wex/{slug}",
                "tier": "wex",
                "snippet": "Exact term page on Cornell's legal dictionary/encyclopedia",
            }
        )
    else:
        search_page = get(
            "https://www.law.cornell.edu/search",
            params={"query": query, "mode": "wex"},
            headers={"User-Agent": WEX_UA},
            timeout=25.0,
        )
        if search_page.status_code == 200:
            import re

            for match in re.finditer(r'href="(/wex/([a-z0-9_]+))"[^>]*>([^<]{3,120})', search_page.text):
                path, _, label = match.groups()
                results.append(
                    {
                        "title": label.strip(),
                        "author": "Cornell Legal Information Institute",
                        "url": f"https://www.law.cornell.edu{path}",
                        "tier": "wex",
                        "snippet": "",
                    }
                )
                if len(results) >= limit:
                    break
    return {"results": results, "note": "Wex: US law definitions & concepts"}