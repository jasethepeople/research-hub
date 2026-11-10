"""Re-embed the whole corpus in place (model upgrades, dimension changes)."""

from __future__ import annotations

import sqlite3
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
    assert_model(connection, target_model)
    return {"reindexed": reindexed, "total": len(documents), "failures": failures}