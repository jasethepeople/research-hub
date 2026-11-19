"""Shared plumbing for HTTP-API-backed MCP tiers (pins + fetch_page)."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hub.fetch import FetchError, fetch_url


class PinBoard:
    """In-memory pin list with the ids the contract expects."""

    def __init__(self, tier: str) -> None:
        self.tier = tier
        self._pins: list[dict[str, Any]] = []

    def pin_result(self, item: dict[str, Any]) -> dict[str, Any]:
        raw = item.get("id") or item.get("md5") or item.get("doi") or len(self._pins)
        pin = {"id": f"{self.tier}:{raw}", "item": item}
        self._pins.append(pin)
        return pin

    def pinned(self) -> list[dict[str, Any]]:
        return list(self._pins)

    def unpin(self, pin_id: str) -> dict[str, Any]:
        before = len(self._pins)
        self._pins[:] = [pin for pin in self._pins if pin["id"] != pin_id]
        return {"removed": len(self._pins) < before, "id": pin_id}


def fetch_page(url: str) -> str:
    try:
        payload = asyncio.run(fetch_url(url, internal=False))
    except Exception as error:
        return json.dumps({"text": "", "bytes": 0, "note": f"{error.__class__.__name__}: {error}"})
    return json.dumps({"text": payload["text"], "bytes": payload["bytes"], "note": payload["note"]})


__all__ = ["FetchError", "PinBoard", "fetch_page"]
