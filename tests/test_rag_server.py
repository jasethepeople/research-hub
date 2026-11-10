import json
import sys
from pathlib import Path

RAG_SERVER = Path(__file__).resolve().parent.parent / "servers" / "rag_server.py"


def _registry() -> dict:
    return {"rag": {"command": sys.executable, "args": [str(RAG_SERVER)]}}


def _prime_corpus(state: Path) -> None:
    import lib.rag.chunk as chunking
    import lib.rag.db as rag_db
    from lib.rag.embed import hash_embed

    state.mkdir(parents=True, exist_ok=True)
    connection = rag_db.open_db(rag_db.state_db_path(str(state)))
    rag_db.initialize(connection)
    rag_db.set_model(connection, "hash-test", 384)
    text = "surface codes tolerate depolarizing noise on quantum hardware"
    chunks = chunking.chunk_text(text)
    rag_db.add_document(
        connection,
        md5="a" * 32,
        title="Quantum Error Correction",
        source="fixture",
        text=text,
        n_pages=1,
        chunks=chunks,
        embeddings=hash_embed(chunks),
    )
    connection.close()


def _server_module(state):
    import importlib
    import os

    os.environ["HUB_STATE"] = str(state)
    for name in ("lib.rag.db", "servers.rag_server"):
        if name in sys.modules:
            del sys.modules[name]
    sys.path.insert(0, str(RAG_SERVER.parent.parent))
    return importlib.import_module("servers.rag_server")


def test_required_and_ask_index_tools_registered(tmp_path):
    module = _server_module(tmp_path / "state")
    for tool_name in ("search", "fetch_page", "pin_result", "pinned", "unpin", "rag_ask", "rag_index"):
        assert callable(getattr(module, tool_name, None)), f"missing {tool_name}"


def test_rag_search_finds_primed_document(tmp_path):
    state = tmp_path / "state"
    _prime_corpus(state)
    module = _server_module(state)
    payload = json.loads(module.search("surface codes depolarizing"))
    assert payload["results"], payload
    assert payload["results"][0]["title"] == "Quantum Error Correction"
    assert payload["results"][0]["tier"] == "rag"
    assert payload["note"] == ""


def test_rag_search_empty_corpus_notes_unavailable_or_empty(tmp_path):
    module = _server_module(tmp_path / "fresh-state")
    payload = json.loads(module.search("anything"))
    assert payload["results"] == []


def test_rag_ask_with_injected_llm_cites(tmp_path, monkeypatch):
    state = tmp_path / "state"
    _prime_corpus(state)
    module = _server_module(state)
    monkeypatch.setattr(module, "get_embedder", lambda: _HashEmbedder())
    monkeypatch.setattr("lib.rag.answer.llm_complete", lambda prompt: "Surface codes help. [1]")
    payload = json.loads(module.rag_ask("surface codes"))
    assert payload["answer"] == "Surface codes help. [1]"
    assert payload["citations"] and payload["citations"][0]["n"] == 1
    assert payload["note"] == ""


def test_rag_index_ingests_local_file(tmp_path, monkeypatch):
    state = tmp_path / "state"
    module = _server_module(state)
    monkeypatch.setattr(module, "get_embedder", lambda: _HashEmbedder())
    document = tmp_path / "doc.txt"
    document.write_text("direction finding with HF radio bearings", encoding="utf-8")
    payload = json.loads(module.rag_index(str(document)))
    assert payload["indexed"] is True, payload
    import lib.rag.db as rag_db

    connection = rag_db.open_db(rag_db.state_db_path(str(state)))
    assert rag_db.get_document(connection, "b" * 32) is None
    docs = rag_db.list_documents(connection)
    assert len(docs) == 1 and docs[0]["title"] == "doc.txt"


class _HashEmbedder:
    model_name = "hash-test"

    def encode(self, texts):
        from lib.rag.embed import hash_embed

        return hash_embed(texts)


def test_rag_index_respects_ingest_windows(tmp_path, monkeypatch):
    module = _server_module(tmp_path / "state")
    monkeypatch.setenv("INGEST_WINDOWS", "03:00-04:00")
    document = tmp_path / "doc.txt"
    document.write_text("some text", encoding="utf-8")
    payload = json.loads(module.rag_index(str(document)))
    assert payload["indexed"] is False
    assert "window" in payload["note"].lower()
