"""SQLite + sqlite-vec store for the RAG tier.

Lives at ``HUB_STATE/rag.sqlite3``. WAL mode, external-content FTS5 index kept
in sync by triggers, and a vec0 virtual table for 384-float embeddings.
``doc_id`` is ``sha1(md5)[:16]`` so every surface (corpus, pending pins,
curate export) keys documents by the content hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.rag import RagUnavailable
from lib.rag.errors import EmbedMismatch

EMBED_DIM = 384
DEFAULT_STATE_DIR = "~/.local/share/intel-hub"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS corpus (
    doc_id TEXT PRIMARY KEY,
    md5 TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    n_pages INTEGER NOT NULL DEFAULT 0,
    n_chunks INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL REFERENCES corpus(doc_id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    page INTEGER NOT NULL DEFAULT 1,
    page_end INTEGER,
    UNIQUE(doc_id, idx)
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='chunk_id'
);
CREATE TRIGGER IF NOT EXISTS chunks_fts_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.chunk_id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_fts_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.chunk_id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_fts_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.chunk_id, old.text);
    INSERT INTO chunks_fts(rowid, text) VALUES (new.chunk_id, new.text);
END;
CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[384]);
CREATE TABLE IF NOT EXISTS corpus_daily (
    day TEXT PRIMARY KEY,
    docs INTEGER NOT NULL DEFAULT 0,
    bytes INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pending_pins (
    md5 TEXT PRIMARY KEY,
    item_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


def state_db_path(state_dir: str | os.PathLike[str] | None = None) -> Path:
    base = Path(state_dir or os.environ.get("HUB_STATE") or DEFAULT_STATE_DIR).expanduser()
    return base / "rag.sqlite3"


def _load_vec(connection: sqlite3.Connection) -> None:
    try:
        import sqlite_vec
    except ImportError as error:
        raise RagUnavailable("sqlite-vec is not installed (install the [rag] extra)") from error
    try:
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
    except AttributeError as error:
        raise RagUnavailable("this SQLite build cannot load extensions") from error


def connect(path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    target = Path(path) if path is not None else state_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    _load_vec(connection)
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    with connection:
        connection.executescript(SCHEMA)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(chunks)").fetchall()}
        if "page_end" not in columns:
            connection.execute("ALTER TABLE chunks ADD COLUMN page_end INTEGER")
            connection.execute("ALTER TABLE chunks ADD COLUMN page INTEGER NOT NULL DEFAULT 1")


def open_db(path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    target = Path(path) if path is not None else state_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(target)
    initialize(connection)
    return connection


def get_meta(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    with connection:
        connection.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def set_model(connection: sqlite3.Connection, model: str, dim: int = EMBED_DIM) -> None:
    """Record (or overwrite) the embedding model identity for this corpus."""
    with connection:
        set_meta(connection, "embed_model", model)
        set_meta(connection, "embed_dim", str(int(dim)))


def assert_model(connection: sqlite3.Connection, model: str | None = None, dim: int | None = None) -> str | None:
    stored_model = get_meta(connection, "embed_model")
    stored_dim = get_meta(connection, "embed_dim")
    if stored_dim is not None and dim is not None and int(stored_dim) != dim:
        raise EmbedMismatch(f"corpus embedding dim is {stored_dim}; refusing to mix with {dim}")
    if stored_model is not None and model is not None and stored_model != model:
        raise EmbedMismatch(
            f"corpus was embedded with model {stored_model!r}; refusing to mix with {model!r}"
        )
    if stored_model is None and model is not None:
        set_meta(connection, "embed_model", model)
        set_meta(connection, "embed_dim", str(dim if dim is not None else EMBED_DIM))
    return stored_model


def doc_id_for(md5: str) -> str:
    return hashlib.sha1(md5.encode("utf-8")).hexdigest()[:16]


def _serialize(vector: list[float]) -> bytes:
    import sqlite_vec

    return sqlite_vec.serialize_float32(vector)


def add_document(
    connection: sqlite3.Connection,
    *,
    md5: str,
    title: str,
    source: str,
    text: str,
    n_pages: int,
    chunks: list[str],
    embeddings: list[list[float]],
    path: str = "",
    chunk_pages: Sequence[int] | None = None,
    chunk_page_ends: Sequence[int | None] | None = None,
) -> str:
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings must have the same length")
    if any(len(vector) != EMBED_DIM for vector in embeddings):
        raise ValueError(f"embeddings must have exactly {EMBED_DIM} dimensions")
    identifier = doc_id_for(md5)
    now = time.time()
    with connection:
        connection.execute(
            "DELETE FROM vec_chunks WHERE rowid IN (SELECT chunk_id FROM chunks WHERE doc_id = ?)",
            (identifier,),
        )
        connection.execute(
            "INSERT INTO corpus (doc_id, md5, title, source, path, text, n_pages, n_chunks, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (identifier, md5, title, source, path, text, n_pages, len(chunks), now),
        )
        pages = list(chunk_pages) if chunk_pages is not None else [1] * len(chunks)
        if len(pages) != len(chunks):
            raise ValueError("chunk_pages must match chunks in length when given")
        ends = list(chunk_page_ends) if chunk_page_ends is not None else [None] * len(chunks)
        if len(ends) != len(chunks):
            raise ValueError("chunk_page_ends must match chunks in length when given")
        connection.executemany(
            "INSERT INTO chunks (doc_id, idx, text, page, page_end) VALUES (?, ?, ?, ?, ?)",
            [
                (identifier, index, chunk, pages[index], ends[index])
                for index, chunk in enumerate(chunks)
            ],
        )
        chunk_rows = connection.execute(
            "SELECT chunk_id FROM chunks WHERE doc_id = ? ORDER BY idx", (identifier,)
        ).fetchall()
        connection.executemany(
            "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
            [(row[0], _serialize(vector)) for row, vector in zip(chunk_rows, embeddings, strict=True)],
        )
        day = datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")
        connection.execute(
            "INSERT INTO corpus_daily (day, docs, bytes) VALUES (?, 1, ?) "
            "ON CONFLICT(day) DO UPDATE SET docs = docs + 1, bytes = bytes + ?",
            (day, len(text), len(text)),
        )
    return identifier


def remove_document(
    connection: sqlite3.Connection,
    *,
    md5: str | None = None,
    doc_id: str | None = None,
    force: bool = False,
) -> bool:
    identifier = doc_id or (doc_id_for(md5) if md5 else None)
    if identifier is None:
        raise ValueError("remove_document needs an md5 or a doc_id")
    from lib.rag.guard import check_shrink

    check_shrink(connection, 1, force=force)
    with connection:
        found = connection.execute("SELECT 1 FROM corpus WHERE doc_id = ?", (identifier,)).fetchone()
        if not found:
            return False
        connection.execute(
            "DELETE FROM vec_chunks WHERE rowid IN (SELECT chunk_id FROM chunks WHERE doc_id = ?)",
            (identifier,),
        )
        connection.execute("DELETE FROM chunks WHERE doc_id = ?", (identifier,))
        connection.execute("DELETE FROM corpus WHERE doc_id = ?", (identifier,))
    return True


def get_document(connection: sqlite3.Connection, md5: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM corpus WHERE md5 = ?", (md5,)).fetchone()
    return dict(row) if row else None


def list_documents(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            "SELECT doc_id, md5, title, source, path, text, n_pages, n_chunks, created_at "
            "FROM corpus ORDER BY created_at DESC"
        ).fetchall()
    ]


def add_pending_pin(connection: sqlite3.Connection, item: dict[str, Any]) -> dict[str, Any]:
    md5 = str(item.get("md5") or "")
    if not md5:
        raise ValueError("pending pins are keyed by md5; item must carry an md5")
    now = time.time()
    with connection:
        connection.execute(
            "INSERT INTO pending_pins (md5, item_json, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(md5) DO UPDATE SET item_json = excluded.item_json, created_at = excluded.created_at",
            (md5, json.dumps(item, ensure_ascii=False), now),
        )
    return {"id": md5, "md5": md5, "item": item, "pending": True}


def list_pending_pins(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        {"id": row["md5"], "md5": row["md5"], "item": json.loads(row["item_json"]), "pending": True}
        for row in connection.execute("SELECT * FROM pending_pins ORDER BY created_at DESC").fetchall()
    ]


def remove_pending_pin(connection: sqlite3.Connection, md5: str) -> bool:
    with connection:
        cursor = connection.execute("DELETE FROM pending_pins WHERE md5 = ?", (md5,))
        return cursor.rowcount > 0
