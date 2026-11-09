import asyncio
import json
from typing import Any

from hub.cache import ResponseCache
from hub.registry import REQUIRED_TOOLS, Registry, Tier


def normalize_query(query: str) -> str:
    return " ".join(query.casefold().split())


def title_key(title: str) -> str:
    return "".join(character for character in title.lower() if character.isalnum())[:60]


async def _search_tier(tier: Tier, cache: ResponseCache, query: str, timeout: float) -> dict[str, Any]:
    cache_key = (tier.name, normalize_query(query))
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    async def invoke():
        value = await tier.call("search", {"query": query, "limit": 20})
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict) or not isinstance(value.get("results"), list):
            raise ValueError("search must return a JSON object with a results array")
        results = []
        for item in value["results"]:
            if not isinstance(item, dict) or not isinstance(item.get("title"), str):
                raise ValueError("each search result must include a string title")
            results.append(
                {
                    "title": item["title"],
                    "author": str(item.get("author") or ""),
                    "url": str(item.get("url") or ""),
                    "tier": tier.name,
                }
            )
        return {"results": results, "note": str(value.get("note") or "")}

    response = await asyncio.wait_for(invoke(), timeout=timeout)
    cache.put(cache_key, response)
    return response


async def search_all(
    registry: Registry, cache: ResponseCache, query: str, limit: int, timeout: float
) -> dict[str, Any]:
    tiers = list(registry.tiers.values())
    gathered = await asyncio.gather(
        *(_search_tier(tier, cache, query, timeout) for tier in tiers),
        return_exceptions=True,
    )
    notes: dict[str, dict[str, str]] = {}
    merged: dict[str, dict[str, Any]] = {}

    for tier, outcome in zip(tiers, gathered, strict=True):
        if isinstance(outcome, BaseException):
            if tier.session is not None:
                tier.state = "degraded"
            note = f"{outcome.__class__.__name__}: {outcome}"
            if not str(outcome):
                note = outcome.__class__.__name__
            tier.detail = note
            notes[tier.name] = {"state": tier.state, "note": note}
            continue
        if tier.session is not None and REQUIRED_TOOLS <= tier.tools:
            tier.state = "ok"
            tier.detail = ""
        notes[tier.name] = {"state": tier.state, "note": outcome["note"] or tier.detail}
        for item in outcome["results"]:
            key = title_key(item["title"])
            if key in merged:
                other_tiers = merged[key]["also_on"]
                if merged[key]["tier"] != tier.name and tier.name not in other_tiers:
                    other_tiers.append(tier.name)
                continue
            merged[key] = {**item, "also_on": []}

    return {"results": list(merged.values())[:limit], "notes": notes}
