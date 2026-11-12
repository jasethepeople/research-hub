"""Ingestion pipeline: download (own downloader), extract, OCR-fallback, chunk, embed, store."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from lib.rag import chunk as chunking
from lib.rag import db, extract, fetch, gate


def _md5_for(source: str) -> str:
    return hashlib.md5(source.encode("utf-8")).hexdigest()


def ingest_document(
    path: Path,
    *,
    connection: sqlite3.Connection | None = None,
    embedder: Any = None,
    title: str = "",
    model: str = "",
    md5: str | None = None,
) -> dict[str, Any]:
    """Ingest a local file; raises ScannedDoc when OCR is required."""
    if not gate.can_ingest()[0]:
        raise RuntimeError("ingestion refused: outside INGEST_WINDOWS")
    if connection is None:
        connection = db.connect()
        db.initialize(connection)
    outcome = extract.extract_text(path)
    doc_md5 = md5 or hashlib.md5(path.read_bytes()).hexdigest()
    return _store(
        connection,
        md5=doc_md5,
        title=title or path.name,
        source=str(path),
        text=outcome["text"],
        n_pages=outcome["n_pages"],
        pages=outcome.get("pages"),
        embedder=embedder,
        model=model,
    )


def ingest_url(
    url: str,
    *,
    connection: sqlite3.Connection | None = None,
    embedder: Any = None,
    title: str = "",
    model: str = "",
    md5: str | None = None,
) -> dict[str, Any]:
    """Download with the tier's own downloader (never the host's 500 KiB /api/fetch)."""
    doc_md5 = md5 or _md5_for(url)
    downloaded = fetch.download_document(url, md5=doc_md5)
    if not downloaded["path"]:
        return {"indexed": False, "md5": doc_md5, "note": downloaded["note"]}
    return ingest_document(
        Path(downloaded["path"]),
        connection=connection,
        embedder=embedder,
        title=title or Path(downloaded["path"]).name,
        model=model,
        md5=doc_md5,
    )


def _chunk_with_pages(text: str, pages: list[str] | None) -> tuple[list[str], list[int], list[int]]:
    """Chunk the WHOLE document so windows span page breaks, then map each chunk
    to its start page (and, when it spans a break, its end page). Chunks never
    split a fact across an unreachable boundary."""
    if not pages:
        chunks = chunking.chunk_text(text)
        return chunks, [1] * len(chunks), [None] * len(chunks)
    import bisect
    import re

    normalized = [re.sub(r"\s+", " ", page).strip() for page in pages]
    norm_text = " ".join(normalized)
    starts: list[int] = []
    cursor = 0
    for page in normalized:
        starts.append(cursor)
        cursor += len(page) + 1
    chunks: list[str] = []
    chunk_pages: list[int] = []
    chunk_page_ends: list[int] = []
    find_from = 0
    for chunk in chunking.chunk_text(norm_text):
        position = norm_text.find(chunk, find_from)
        if position < 0:
            position = norm_text.find(chunk)
        if position >= 0:
            find_from = position + 1
            page_number = bisect.bisect_right(starts, position)
            end_page = bisect.bisect_right(starts, position + max(len(chunk) - 1, 0))
        else:
            page_number = chunk_pages[-1] if chunk_pages else 1
            end_page = page_number
        chunks.append(chunk)
        chunk_pages.append(page_number)
        chunk_page_ends.append(max(end_page, page_number))
    return chunks, chunk_pages, chunk_page_ends


def _store(
    connection: sqlite3.Connection,
    *,
    md5: str,
    title: str,
    source: str,
    text: str,
    n_pages: int,
    pages: list[str] | None,
    embedder: Any | None,
    model: str,
) -> dict[str, Any]:
    if not text.strip():
        return {"indexed": False, "md5": md5, "note": "no text extracted"}
    chunks, chunk_pages, chunk_page_ends = _chunk_with_pages(text, pages)
    if embedder is None:
        from lib.rag.embed import get_embedder

        embedder = get_embedder()
    embeddings = embedder.encode(list(chunks))
    model_name = model or getattr(embedder, "model_name", "unknown")
    db.assert_model(connection, model_name, len(embeddings[0]) if embeddings else db.EMBED_DIM)
    doc_id = db.add_document(
        connection,
        md5=md5,
        title=title,
        source=source,
        text=text,
        n_pages=n_pages,
        chunks=chunks,
        embeddings=embeddings,
        chunk_pages=chunk_pages,
        chunk_page_ends=chunk_page_ends,
    )
    return {"indexed": True, "md5": md5, "doc_id": doc_id, "chunks": len(chunks), "note": ""}
