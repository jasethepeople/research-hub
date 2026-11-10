"""MCP tier over the local RAG corpus: the five required tools plus rag_ask/rag_index."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hub.fetch import fetch_url
from lib.rag import available, retrieve
from lib.rag import db as rag_db
from lib.rag.answer import answer
from lib.rag.embed import get_embedder
from lib.rag.errors import OcrUnavailable, RagUnavailable, ScannedDoc, UnsupportedFormat
from lib.rag.ingest import ingest_document, ingest_url

TIER = "rag"


def _result(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _unavailable() -> str:
    return _result({"results": [], "note": "rag unavailable: install the [rag] dependency group"})


def _open():
    connection = rag_db.open_db()
    rag_db.initialize(connection)
    return connection


async def search(query: str, limit: int = 20) -> str:
    if not available() or not query.strip():
        return _unavailable()

    def _work() -> list[dict[str, Any]]:
        connection = _open()
        try:
            return retrieve.search(connection, query, mode="hybrid_rerank", limit=limit, embedder=get_embedder())
        finally:
            connection.close()

    try:
        hits = await asyncio.to_thread(_work)
    except RagUnavailable:
        return _unavailable()
    results = [
        {
            "title": hit["title"],
            "author": "",
            "url": f"rag:md5:{hit['md5']}",
            "tier": TIER,
        }
        for hit in hits
    ]
    return _result({"results": results, "note": ""})


async def fetch_page(url: str) -> str:
    try:
        payload = await fetch_url(url, internal=False)
    except Exception as error:  # noqa: BLE001 - report any failure as a note
        return _result({"text": "", "bytes": 0, "note": f"{error.__class__.__name__}: {error}"})
    return _result({"text": payload["text"], "bytes": payload["bytes"], "note": payload["note"]})


def pin_result(item: dict) -> str:
    if not available():
        return _unavailable()
    connection = _open()
    try:
        pin = rag_db.add_pending_pin(connection, item)
    finally:
        connection.close()
    return _result(pin)


def pinned() -> str:
    if not available():
        return _unavailable()
    connection = _open()
    try:
        return _result(rag_db.list_pending_pins(connection))
    finally:
        connection.close()


def unpin(id: str) -> str:
    if not available():
        return _unavailable()
    connection = _open()
    try:
        removed = rag_db.remove_pending_pin(connection, id)
    finally:
        connection.close()
    return _result({"deleted": removed, "id": id})


async def rag_ask(question: str, mode: str = "hybrid_rerank", limit: int = 6) -> str:
    if not available() or not question.strip():
        return _unavailable()

    def _work() -> dict[str, Any]:
        connection = _open()
        try:
            return answer(connection, question, mode=mode, limit=limit, embedder=get_embedder())
        finally:
            connection.close()

    try:
        outcome = await asyncio.to_thread(_work)
    except RagUnavailable:
        return _unavailable()
    return _result(outcome)


async def rag_index(source: str, title: str = "") -> str:
    """Ingest a URL or local file into the local corpus using the tier's own downloader."""
    if not available():
        return _unavailable()

    def _work() -> dict[str, Any]:
        embedder = get_embedder()
        if source.startswith("http://") or source.startswith("https://"):
            return ingest_url(source, title=title, embedder=embedder)
        return ingest_document(Path(source), title=title, embedder=embedder)

    try:
        outcome = await asyncio.to_thread(_work)
    except ScannedDoc:
        return _result({"indexed": False, "note": "scanned document; run ocr_pdf ingestion"})
    except OcrUnavailable as error:
        return _result({"indexed": False, "note": str(error)})
    except UnsupportedFormat as error:
        return _result({"indexed": False, "note": str(error)})
    except Exception as error:  # noqa: BLE001
        return _result({"indexed": False, "note": f"{error.__class__.__name__}: {error}"})
    return _result(outcome)


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(TIER)
    for tool in (search, fetch_page, pin_result, pinned, unpin, rag_ask, rag_index):
        server.tool()(tool)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()