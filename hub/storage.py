import json
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

PIN_LIMIT = 500


class Store:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir.expanduser()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.database = self.state_dir / "hub.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pins (
                    id TEXT PRIMARY KEY,
                    item_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL
                );
                CREATE INDEX IF NOT EXISTS pins_expires_at ON pins(expires_at);
                CREATE TABLE IF NOT EXISTS watches (
                    id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )

    @staticmethod
    def _expiry_timestamp(expires_at: datetime | None) -> float | None:
        if expires_at is None:
            return None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at.timestamp()

    def pin(self, item: dict[str, Any], expires_at: datetime | None = None) -> dict[str, Any]:
        now = time.time()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute(
                "SELECT COUNT(*) FROM pins WHERE expires_at IS NULL OR expires_at > ?", (now,)
            ).fetchone()[0]
            if count >= PIN_LIMIT:
                raise OverflowError(f"Pin limit of {PIN_LIMIT} reached.")
            pin_id = uuid4().hex
            expiry = self._expiry_timestamp(expires_at)
            connection.execute(
                "INSERT INTO pins (id, item_json, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (pin_id, json.dumps(item, ensure_ascii=False), now, expiry),
            )
        return {
            "id": pin_id,
            "item": item,
            "created_at": datetime.fromtimestamp(now, UTC).isoformat(),
            "expires_at": datetime.fromtimestamp(expiry, UTC).isoformat() if expiry is not None else None,
        }

    def list_pins(self) -> list[dict[str, Any]]:
        now = time.time()
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT id, item_json, created_at, expires_at FROM pins "
                "WHERE expires_at IS NULL OR expires_at > ? ORDER BY created_at DESC, id DESC",
                (now,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "item": json.loads(row["item_json"]),
                "created_at": datetime.fromtimestamp(row["created_at"], UTC).isoformat(),
                "expires_at": datetime.fromtimestamp(row["expires_at"], UTC).isoformat()
                if row["expires_at"] is not None
                else None,
            }
            for row in rows
        ]

    def unpin(self, pin_id: str) -> bool:
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM pins WHERE id = ?", (pin_id,))
            return cursor.rowcount > 0

    def sweep_expired(self, now: float | None = None) -> int:
        current = time.time() if now is None else now
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM pins WHERE expires_at IS NOT NULL AND expires_at <= ?", (current,))
            return cursor.rowcount

    def add_watch(self, query: str) -> dict[str, Any]:
        created_at = time.time()
        watch_id = uuid4().hex
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO watches (id, query, created_at) VALUES (?, ?, ?)",
                (watch_id, query.strip(), created_at),
            )
        return {
            "id": watch_id,
            "query": query.strip(),
            "created_at": datetime.fromtimestamp(created_at, UTC).isoformat(),
        }

    def list_watches(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT id, query, created_at FROM watches ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "query": row["query"],
                "created_at": datetime.fromtimestamp(row["created_at"], UTC).isoformat(),
            }
            for row in rows
        ]
