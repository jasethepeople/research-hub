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
) -> dict[str, Any]:
    """Ingest a local file; raises ScannedDoc when OCR is required."""
    if not gate.can_ingest()[0]:
        raise RuntimeError("ingestion refused: outside INGEST_WINDOWS")
    if connection is None:
        connection = db.connect()
        db.initialize(connection)
    outcome = extract.extract_text(path)
    doc_md5 = hashlib.md5(path.read_bytes()).hexdigest()
    return _store(
        connection,
        md5=doc_md5,
        title=title or path.name,
        source=str(path),
        text=outcome["text"],
        n_pages=outcome["n_pages"],
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
    )


def _store(
    connection: sqlite3.Connection,
    *,
    md5: str,
    title: str,
    source: str,
    text: str,
    n_pages: int,
    embedder: Any | None,
    model: str,
) -> dict[str, Any]:
    if not text.strip():
        return {"indexed": False, "md5": md5, "note": "no text extracted"}
    chunks = chunking.chunk_text(text)
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
    )
    return {"indexed": True, "md5": md5, "doc_id": doc_id, "chunks": len(chunks), "note": ""}
