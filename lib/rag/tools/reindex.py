"""Re-embed the whole corpus in place (model upgrades, dimension changes)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from lib.rag import chunk as chunking
from lib.rag.db import add_document, assert_model, list_documents, remove_document
from lib.rag.embed import as_embedder


def reindex(
    connection: sqlite3.Connection,
    embedder: Any,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Re-chunk and re-embed every stored document with the given embedder."""
    documents = list_documents(connection)
    target_model = model or getattr(embedder, "model_name", "unknown")
    reindexed = 0
    failures: list[dict[str, str]] = []
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    daily_before = connection.execute(
        "SELECT docs, bytes FROM corpus_daily WHERE day = ?", (today,)
    ).fetchone()
    daily_snapshot = (int(daily_before[0]), int(daily_before[1])) if daily_before else (0, 0)
    for document in documents:
        md5 = document["md5"]
        try:
            chunks = chunking.chunk_text(document["text"])
            vectors = as_embedder(embedder).encode(chunks)
            remove_document(connection, md5=md5, force=True)
            add_document(
                connection,
                md5=md5,
                title=document["title"],
                source=document["source"],
                text=document["text"],
                n_pages=document["n_pages"],
                chunks=chunks,
                embeddings=vectors,
            )
            reindexed += 1
        except Exception as error:  # noqa: BLE001 - keep going; report per doc
            failures.append({"md5": md5, "error": f"{error.__class__.__name__}: {error}"})
    if reindexed:
        assert_model(connection, target_model)
    with connection:
        connection.execute(
            "INSERT INTO corpus_daily (day, docs, bytes) VALUES (?, ?, ?) "
            "ON CONFLICT(day) DO UPDATE SET docs = ?, bytes = ?",
            (today, daily_snapshot[0], daily_snapshot[1], daily_snapshot[0], daily_snapshot[1]),
        )
    return {"reindexed": reindexed, "total": len(documents), "failures": failures}