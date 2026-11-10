"""Ingestion time windows and the evaluation lock."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from lib.rag.errors import EvalLocked


def _parse_hhmm(value: str) -> tuple[int, int]:
    hours, minutes = value.strip().split(":")
    return int(hours), int(minutes)


def parse_windows(spec: str) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Parse an INGEST_WINDOWS spec like '09:00-12:00,14:00-18:00'. Empty spec means no restriction."""
    windows: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        start_text, _, end_text = chunk.partition("-")
        windows.append((_parse_hhmm(start_text), _parse_hhmm(end_text)))
    return windows


def _minutes_of(day_time: tuple[int, int]) -> int:
    return day_time[0] * 60 + day_time[1]


def can_ingest(now: float | None = None, spec: str | None = None) -> tuple[bool, str]:
    """True when ingestion is allowed: no INGEST_WINDOWS set, or now falls inside a window."""
    if spec is None:
        spec = os.environ.get("INGEST_WINDOWS", "")
    windows = parse_windows(spec)
    if not windows:
        return True, ""
    moment = datetime.fromtimestamp(time.time() if now is None else now, UTC)
    current = moment.hour * 60 + moment.minute
    for start, end in windows:
        if _minutes_of(start) <= current < _minutes_of(end):
            return True, ""
    pretty = ", ".join(f"{start[0]:02d}:{start[1]:02d}-{end[0]:02d}:{end[1]:02d}" for start, end in windows)
    return False, f"Outside ingestion windows ({pretty} UTC)."


def eval_lock_path() -> Path:
    state = os.environ.get("HUB_STATE") or "~/.local/share/intel-hub"
    return Path(state).expanduser() / "rag-eval.lock"


@contextmanager
def eval_lock(*, blocking: bool = False, poll_seconds: float = 0.05, timeout_seconds: float = 5.0):
    """Advisory lock so evaluation and ingestion do not run concurrently.

    The lock file is created exclusively under HUB_STATE; a stale lock older than one hour
    is considered abandoned and may be taken over.
    """
    path = eval_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > 3600:
                    path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if not blocking:
                raise EvalLocked(f"Evaluation lock is held: {path}") from None
            if time.monotonic() > deadline:
                raise EvalLocked(f"Evaluation lock wait timed out: {path}") from None
            time.sleep(poll_seconds)
    try:
        os.write(handle, str(os.getpid()).encode())
        yield path
    finally:
        os.close(handle)
        path.unlink(missing_ok=True)