"""arXiv Atom API search."""

import xml.etree.ElementTree as ET

from lib.providers._shadow import API_UA, cache, format_results, get_html

API = "https://export.arxiv.org/api/query"
MIRRORS = ("https://export.arxiv.org",)
ATOM_NS = "http://www.w3.org/2005/Atom"
HEADERS = {"User-Agent": API_UA}


def parse_response(atom_xml: str, limit: int = 20) -> dict:
    root = ET.fromstring(atom_xml)
    if root.tag != f"{{{ATOM_NS}}}feed":
        raise ValueError("arXiv response is not an Atom feed")
    results = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        title = " ".join((entry.findtext(f"{{{ATOM_NS}}}title") or "").split())
        abstract = " ".join((entry.findtext(f"{{{ATOM_NS}}}summary") or "").split())
        url = (entry.findtext(f"{{{ATOM_NS}}}id") or "").strip()
        if not title or not url:
            continue
        authors = [
            " ".join((author.findtext(f"{{{ATOM_NS}}}name") or "").split())
            for author in entry.findall(f"{{{ATOM_NS}}}author")
        ]
        pdf = next(
            (
                link.get("href", "")
                for link in entry.findall(f"{{{ATOM_NS}}}link")
                if link.get("title") == "pdf" and link.get("href")
            ),
            "",
        )
        results.append(
            {
                "title": title,
                "author": ", ".join(name for name in authors if name),
                "url": url,
                "pdf": pdf,
                "snippet": abstract,
            }
        )
    return format_results(results, limit)


@cache
def search(query: str, limit: int = 20) -> dict:
    atom_xml = get_html(
        API,
        params={"search_query": f'all:"{query}"', "start": 0, "max_results": limit},
        headers=HEADERS,
        mirrors=MIRRORS,
    )
    return parse_response(atom_xml, limit)
