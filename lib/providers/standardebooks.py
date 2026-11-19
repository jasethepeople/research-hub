"""Standard Ebooks — curated, high-quality public-domain epub editions."""
import re
from typing import Any

from lib.providers.http import get


def search(query: str, limit: int = 20) -> dict[str, Any]:
    response = get(
        "https://standardebooks.org/ebooks",
        params={"query": query.strip()},
        timeout=30.0,
    )
    blocks = re.split(r'<li typeof="schema:Book"', response.text)[1:]
    results = []
    for block in blocks[: limit * 3]:
        slug = re.search(r'about="(/ebooks/[^"]+)"', block)
        title = re.search(r'property="schema:name">([^<]+)</span>', block)
        if not slug or not title:
            continue
        results.append(
            {
                "id": slug.group(1),
                "title": title.group(1),
                "author": "",
                "url": "https://standardebooks.org" + slug.group(1),
                "source": "Standard Ebooks",
            }
        )
        if len(results) >= limit:
            break
    return {"results": results, "note": ""}
