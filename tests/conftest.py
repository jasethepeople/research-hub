import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hub.app import create_app
from hub.config import DEPLOY_DIR, Settings


def _rag_available():
    try:
        import aiosqlite  # noqa: F401
        import ebooklib  # noqa: F401
        import fitz  # noqa: F401
        import sqlite_vec  # noqa: F401
        from bs4 import BeautifulSoup  # noqa: F401
    except ImportError:
        return False
    return True

STUB = Path(__file__).parent / "stubs" / "stub_server.py"


def stub_config(name: str, mode: str = "ok") -> dict:
    return {
        name: {
            "command": sys.executable,
            "args": [str(STUB), "--mode", mode, "--tier", name],
            "metadata": {"ignored_extra": True},
        }
    }


@pytest.fixture
def make_client(tmp_path):
    clients = []

    def build(config: dict, timeout: float = 12, fourth_pane: bool = False) -> TestClient:
        registry_path = tmp_path / "mcp_servers.json"
        registry_path.write_text(json.dumps(config), encoding="utf-8")
        settings = Settings(
            deploy_dir=DEPLOY_DIR,
            state_dir=tmp_path / "state",
            port=8471,
            tier_timeout=timeout,
            fourth_pane=fourth_pane,
            registry_path=registry_path,
        )
        client = TestClient(create_app(settings))
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.close()


@pytest.fixture
def corpus(tmp_path):
    if not _rag_available():
        pytest.skip("rag extras not installed")
    import lib.rag.db as rag_db
    from lib.rag.chunk import chunk_text
    from lib.rag.embed import hash_embed
    from tests.test_rag_core import DOCS

    connection = rag_db.connect(tmp_path / "rag.sqlite3")
    rag_db.initialize(connection)
    for md5, title, text in DOCS:
        chunks = chunk_text(text)
        rag_db.add_document(
            connection,
            md5=md5,
            title=title,
            source="fixture",
            text=text,
            n_pages=1,
            chunks=chunks,
            embeddings=hash_embed(chunks),
        )
    return connection
