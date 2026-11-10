"""Anna's Archive MCP tier: a thin FastMCP wrapper around lib.annas.

Runs over stdio like every other tier. Credentials come from the environment
(ANNAS_KEY); the registry never carries them.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hub.fetch import fetch_url
from lib.annas import AnnaArchive


def _result(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


archive = AnnaArchive()


def search(query: str, limit: int = 20) -> str:
    outcome = archive.search(query, limit=limit)
    results = [
        {"title": item["title"], "author": item["author"], "url": item["url"], "tier": "annas"}
        for item in outcome["results"]
    ]
    return _result({"results": results, "note": outcome["note"]})


def fetch_page(url: str) -> str:
    try:
        payload = asyncio.run(fetch_url(url, internal=False))
    except Exception as error:
        return _result({"text": "", "bytes": 0, "note": f"{error.__class__.__name__}: {error}"})
    return _result({"text": payload["text"], "bytes": payload["bytes"], "note": payload["note"]})


def pin_result(item: dict) -> str:
    return _result(archive.pin_result(item))


def pinned() -> str:
    return _result(archive.pinned())


def unpin(id: str) -> str:
    return _result(archive.unpin(id))


def download(md5: str) -> str:
    return _result(archive.download(md5))


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("annas")
    server.tool()(search)
    server.tool()(fetch_page)
    server.tool()(pin_result)
    server.tool()(pinned)
    server.tool()(unpin)
    server.tool()(download)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()