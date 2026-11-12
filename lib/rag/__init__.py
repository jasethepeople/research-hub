"""Availability probe for the optional [rag] extra.

The RAG tier must degrade cleanly: when the optional dependencies are absent,
the server still starts and every tool answers with an ``unavailable`` note
instead of crashing the MCP session.
"""

from __future__ import annotations

from lib.rag.errors import RagUnavailable

CORE_MODULES = ("sqlite_vec", "fitz", "ebooklib", "bs4", "aiosqlite")

__all__ = ["CORE_MODULES", "RagUnavailable", "available", "missing_modules", "require"]


def missing_modules() -> list[str]:
    import importlib.util

    return [name for name in CORE_MODULES if importlib.util.find_spec(name) is None]


def available() -> bool:
    return not missing_modules()


def require() -> None:
    missing = missing_modules()
    if missing:
        raise RagUnavailable("RAG dependencies missing: " + ", ".join(missing) + " (install the [rag] extra)")