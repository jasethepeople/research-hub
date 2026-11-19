"""Hugging Face tier: model + dataset search."""

from typing import Any

from lib.providers.http import get

API = "https://huggingface.co/api"


def search(query: str, limit: int = 20) -> dict[str, Any]:
    per_page = min(max(limit, 1), 50)
    half = max(per_page // 2, 1)
    models_response = get(
        f"{API}/models",
        params={"search": query.strip(), "limit": half, "sort": "downloads", "direction": -1},
        timeout=30.0,
    )
    datasets_response = get(
        f"{API}/datasets",
        params={"search": query.strip(), "limit": max(per_page - half, 1), "sort": "downloads"},
        timeout=30.0,
    )
    results = []
    for item in models_response.json()[:half]:
        name = str(item.get("id") or item.get("modelId") or "")
        if not name:
            continue
        byline = " · ".join(
            part
            for part in (
                "model",
                item.get("pipeline_tag") or "",
                f"↓ {item.get('downloads', 0)}" if item.get("downloads") else "",
            )
            if part
        )
        results.append(
            {
                "title": name,
                "url": f"https://huggingface.co/{name}",
                "author": byline,
                "published": str(item.get("createdAt") or "")[:10],
                "source": "HF",
                "id": name,
            }
        )
    for item in datasets_response.json()[: max(per_page - half, 1)]:
        name = str(item.get("id") or "")
        if not name:
            continue
        results.append(
            {
                "title": name,
                "url": f"https://huggingface.co/datasets/{name}",
                "author": "dataset",
                "published": str(item.get("createdAt") or "")[:10],
                "source": "HF",
                "id": name,
            }
        )
    return {"results": results, "note": ""}