"""Corpus curation: md5-keyed export/import, pending-pin pruning, guarded removal."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from lib.rag import guard
from lib.rag.db import add_document, get_document, list_pending_pins, remove_document
from lib.rag.embed import as_embedder


def export(connection: sqlite3.Connection, out_path: str | Path) -> dict[str, Any]:
    payload = {
        "docs": [
            {
                "md5": row["md5"],
                "title": row["title"],
                "source": row["source"],
                "path": row["path"],
                "text": row["text"],
                "n_pages": row["n_pages"],
            }
            for row in _all_documents(connection)
        ],
        "pending_pins": list_pending_pins(connection),
    }
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"exported": len(payload["docs"]), "pending_pins": len(payload["pending_pins"]), "path": str(out_path)}


def _all_documents(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    from lib.rag.db import list_documents

    return list_documents(connection)


def import_docs(
    connection: sqlite3.Connection,
    in_path: str | Path,
    embedder: Any,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    from lib.rag.chunk import chunk_text

    payload = json.loads(Path(in_path).read_text(encoding="utf-8"))
    imported = 0
    skipped = 0
    for doc in payload.get("docs", []):
        md5 = doc["md5"]
        if get_document(connection, md5) is not None:
            if not replace:
                skipped += 1
                continue
            remove_document(connection, md5=md5, force=True)
        chunks = chunk_text(doc.get("text", ""))
        add_document(
            connection,
            md5=md5,
            title=doc.get("title") or md5,
            source=doc.get("source") or "curate-import",
            path=doc.get("path") or "",
            text=doc.get("text", ""),
            n_pages=int(doc.get("n_pages") or 0),
            chunks=chunks,
            embeddings=as_embedder(embedder).encode(chunks),
        )
        imported += 1
    return {"imported": imported, "skipped_existing": skipped}


def prune_pending(connection: sqlite3.Connection) -> dict[str, Any]:
    from lib.rag.db import remove_pending_pin

    pruned = 0
    for pin in list_pending_pins(connection):
        if remove_pending_pin(connection, pin["md5"]):
            pruned += 1
    return {"pruned": pruned}


def remove(connection: sqlite3.Connection, md5: str, *, force: bool = False) -> dict[str, Any]:
    """Remove one document, honoring the 24h-baseline shrink guard unless forced."""
    if get_document(connection, md5) is None:
        return {"removed": False, "note": "unknown md5"}
    guard.check_shrink(connection, 1, force=force)
    removed = remove_document(connection, md5=md5)
    return {"removed": removed, "note": ""}


