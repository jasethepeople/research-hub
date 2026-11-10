"""Corpus-volume guard: records ingestion and blocks shrink operations past the 24h baseline."""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime

from lib.rag.errors import ShrinkBlocked


def record_ingest(
    connection: sqlite3.Connection,
    docs: int = 1,
    bytes_written: int = 0,
    now: float | None = None,
) -> None:
    """Bump the corpus_daily counter (kept in sync with db.add_document; safe to call again)."""
    if docs <= 0:
        return
    moment = time.time() if now is None else now
    day = datetime.fromtimestamp(moment, UTC).strftime("%Y-%m-%d")
    with connection:
        connection.execute(
            "INSERT INTO corpus_daily (day, docs, bytes) VALUES (?, ?, ?) "
            "ON CONFLICT(day) DO UPDATE SET docs = docs + ?, bytes = bytes + ?",
            (day, docs, bytes_written, docs, bytes_written),
        )


def baseline_24h(connection: sqlite3.Connection, now: float | None = None) -> int:
    """Documents ingested in the trailing 24 hours (spans at most two UTC day buckets)."""
    moment = time.time() if now is None else now
    start = datetime.fromtimestamp(moment - 86_400, UTC).strftime("%Y-%m-%d")
    end = datetime.fromtimestamp(moment, UTC).strftime("%Y-%m-%d")
    row = connection.execute(
        "SELECT COALESCE(SUM(docs), 0) FROM corpus_daily WHERE day >= ? AND day <= ?",
        (start, end),
    ).fetchone()
    return int(row[0])


def created_before(connection: sqlite3.Connection, cutoff: float) -> int:
    row = connection.execute("SELECT COUNT(*) FROM corpus WHERE created_at < ?", (cutoff,)).fetchone()
    return int(row[0])


def check_shrink(
    connection: sqlite3.Connection,
    removals: int,
    *,
    force: bool = False,
    now: float | None = None,
) -> None:
    """Refuse removing more documents than the trailing-24h ingestion baseline unless forced.

    The baseline exists so an over-eager prune cannot gut a corpus that is not being
    replenished; force=True is the explicit operator override.
    """
    if removals <= 0 or force:
        return
    baseline = baseline_24h(connection, now)
    if removals > baseline:
        moment = time.time() if now is None else now
        window_start = datetime.fromtimestamp(moment - 86_400, UTC).strftime("%Y-%m-%d")
        raise ShrinkBlocked(
            f"Removing {removals} document(s) exceeds the 24h ingestion baseline of {baseline} "
            f"(since {window_start}); pass force to override."
        )