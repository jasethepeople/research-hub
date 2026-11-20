"""Generic MCP tier over a lib.providers search module.

Usage: python servers/web_server.py <provider>
Providers implement search(query, limit) -> {"results": [...], "note": str}
with each result carrying at least title/author/url.
"""

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tierbase import PinBoard, fetch_page

PROVIDERS = (
    "openlibrary", "internetarchive", "arxiv", "crossref", "libgen", "scihub",
    "nvd", "exploitdb", "osv", "github", "gitlab", "npm", "huggingface",
    "apkmirror", "openalex", "pubmed", "europemc", "doaj",
    "standardebooks", "librivox", "crates", "rubygems", "maven", "packagist",
    "dockerhub", "flathub", "aur", "fdroid", "cisa-kev", "ghadvisories",
    "metasploit", "wikipedia", "stackexchange", "hackernews",
    "wikimedia", "artic", "openverse", "ia-video", "metmuseum", "smithsonian",
)


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in PROVIDERS:
        print(f"unknown provider: {name!r}; expected one of {PROVIDERS}", file=sys.stderr)
        raise SystemExit(2)
    provider = importlib.import_module(f"lib.providers.{name.replace(chr(45), chr(95))}")
    board = PinBoard(name)

    def search(query: str, limit: int = 20) -> str:
        try:
            outcome = provider.search(query, limit=limit)
        except Exception as error:
            return json.dumps(
                {"results": [], "note": f"{error.__class__.__name__}: {error}"}, ensure_ascii=False
            )
        results = [
            {
                "title": str(item["title"]),
                "author": str(item.get("author") or ""),
                "url": str(item.get("url") or ""),
                **({"link": str(item["link"])} if item.get("link") else {}),
                **({"snippet": str(item["snippet"])} if item.get("snippet") else {}),
            }
            for item in outcome["results"]
        ]
        return json.dumps({"results": results, "note": outcome.get("note", "")}, ensure_ascii=False)

    def pin_result(item: dict) -> str:
        return json.dumps(board.pin_result(item), ensure_ascii=False)

    def pinned() -> str:
        return json.dumps(board.pinned(), ensure_ascii=False)

    def unpin(id: str) -> str:
        return json.dumps(board.unpin(id), ensure_ascii=False)

    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)
    server.tool()(search)
    server.tool()(fetch_page)
    server.tool()(pin_result)
    server.tool()(pinned)
    server.tool()(unpin)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
