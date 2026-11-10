"""Cite-only answering over retrieved passages with an OpenAI-compatible LLM."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from lib.rag.retrieve import search

SYSTEM_PROMPT = (
    "You answer strictly from the numbered passages provided. "
    "Every factual claim must carry a bracketed citation like [2] referring to the "
    "passage number that supports it. If the passages do not contain the answer, "
    "reply exactly: not in corpus."
)

DEFAULT_LLM_MODEL = "local-model"


def llm_base_url() -> str:
    return (os.environ.get("LLM_BASE_URL") or "").rstrip("/")


def llm_complete(
    prompt: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = 60.0,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """POST one chat completion against an OpenAI-compatible endpoint."""
    base = (base_url or llm_base_url()).rstrip("/")
    if not base:
        raise RuntimeError("no LLM endpoint configured")
    key = api_key if api_key is not None else os.environ.get("LLM_API_KEY", "")
    model_name = model or os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL
    response = httpx.Client(timeout=timeout, transport=transport).post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"} if key else {},
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["choices"][0]["message"]["content"])


def build_prompt(question: str, passages: Sequence[dict[str, Any]]) -> str:
    blocks = ["Answer ONLY from the numbered passages below. Cite each claim as [n]."]
    for index, passage in enumerate(passages, start=1):
        blocks.append(f"[{index}] ({passage.get('title', '')}) {passage.get('text', '')}")
    blocks.append(f"Question: {question}")
    return "\n\n".join(blocks)


def citations_for(passages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "n": index,
            "title": passage.get("title", ""),
            "md5": passage.get("md5", ""),
            "chunk_id": passage.get("chunk_id"),
        }
        for index, passage in enumerate(passages, start=1)
    ]


def answer(
    connection,
    question: str,
    *,
    mode: str = "hybrid_rerank",
    limit: int = 6,
    embedder=None,
    reranker=None,
    complete: Callable[..., str] | None = None,
) -> dict[str, Any]:
    """Retrieve passages, then answer strictly with citations. Never fabricates without them."""
    passages = search(connection, question, mode=mode, limit=limit, embedder=embedder, reranker=reranker)
    if not passages:
        return {"answer": "", "citations": [], "note": "no passages retrieved"}
    prompt = build_prompt(question, passages)
    try:
        complete = complete or llm_complete
        text = complete(prompt)
    except RuntimeError as error:
        return {"answer": "", "citations": citations_for(passages), "note": f"llm_unavailable: {error}"}
    except Exception as error:
        return {"answer": "", "citations": citations_for(passages), "note": f"{error.__class__.__name__}: {error}"}
    cited = {int(token[1:-1]) for token in re.findall(r"\[\d+\]", text)}
    used = sorted(number for number in cited if 1 <= number <= len(passages))
    citations = [entry for entry in citations_for(passages) if entry["n"] in used] or citations_for(passages)
    return {"answer": text, "citations": citations, "note": ""}
