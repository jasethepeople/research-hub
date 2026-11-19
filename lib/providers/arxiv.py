"""arXiv tier (open), Atom API."""

import xml.etree.ElementTree as ET

from lib.providers.http import get

ATOM = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}


def search(query: str, limit: int = 20) -> dict:
    response = get(
        ATOM,
        params={
            "search_query": f'all:"{query.strip()}"',
            "start": 0,
            "max_results": min(max(limit, 1), 50),
        },
        timeout=30.0,
    )
    root = ET.fromstring(response.text)
    results = []
    for entry in root.findall("a:entry", NS):
        pdf_links = (node.attrib.get("href", "") for node in entry.findall("a:link", NS))
        link = next((href for href in pdf_links if "arxiv.org/pdf" in href or href.endswith(".pdf")), "")
        summary = " ".join((entry.findtext("a:summary", "", NS) or "").split())[:400]
        results.append(
            {
                "title": " ".join((entry.findtext("a:title", "", NS) or "").split()),
                "author": ", ".join(
                    " ".join((author.findtext("a:name", "", NS) or "").split())
                    for author in entry.findall("a:author", NS)
                ),
                "url": (entry.findtext("a:id", "", NS) or "").strip(),
                "pdf": link,
                "summary": summary,
            }
        )
    return {"results": results, "note": ""}
