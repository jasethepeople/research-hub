import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

parser = argparse.ArgumentParser()
parser.add_argument("--mode", default="ok")
parser.add_argument("--tier", default="stub")
args = parser.parse_args()
fixture = json.loads(Path(__file__).with_name("fixture.json").read_text(encoding="utf-8"))
server = FastMCP(args.tier)
pins: list[dict] = []


@server.tool()
def search(query: str, limit: int = 20) -> str:
    if args.mode == "raise":
        raise RuntimeError("stub search raised as requested")
    if args.mode == "sleep":
        time.sleep(1.0)
    if args.mode == "exit":
        os._exit(17)
    results = []
    for item in fixture["results"][:limit]:
        results.append({**item, "tier": args.tier})
    return json.dumps({"results": results, "note": fixture.get("note", "")})


@server.tool()
def fetch_page(url: str) -> str:
    return json.dumps(fixture["page"])


@server.tool()
def pin_result(item: dict) -> str:
    pin = {"id": uuid4().hex, "item": item}
    pins.append(pin)
    return json.dumps(pin)


@server.tool()
def pinned() -> str:
    return json.dumps(pins)


@server.tool()
def unpin(id: str) -> str:
    before = len(pins)
    pins[:] = [pin for pin in pins if pin["id"] != id]
    return json.dumps({"deleted": len(pins) < before, "id": id})


server.run(transport="stdio")
