import json

import pytest

from lib.rag.embed import hash_embed
from lib.rag.tools import curate, eval_rag, golden_coverage, reindex


@pytest.fixture
def corpus(tmp_path):
    import lib.rag.db as rag_db

    connection = rag_db.connect(tmp_path / "rag.sqlite3")
    rag_db.initialize(connection)
    connection.execute(
        "INSERT INTO pending_pins (md5, item_json, created_at) VALUES (?, ?, 0)",
        ("f" * 32, '{"title": "later"}'),
    )
    connection.commit()
    return connection


def _ingest(connection, md5, title, text):
    from lib.rag.chunk import chunk_text
    from lib.rag.db import add_document

    chunks = chunk_text(text)
    add_document(
        connection,
        md5=md5,
        title=title,
        source="test",
        text=text,
        n_pages=1,
        chunks=chunks,
        embeddings=hash_embed(chunks),
    )


def test_curate_export_import_roundtrip_is_md5_keyed(corpus, tmp_path):
    _ingest(corpus, "a" * 32, "Alpha Doc", "alpha corpus text")
    _ingest(corpus, "b" * 32, "Beta Doc", "beta corpus text")
    out_path = tmp_path / "export.json"
    exported = curate.export(corpus, out_path)
    assert exported["exported"] == 2
    assert exported["pending_pins"] == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert {doc["md5"] for doc in payload["docs"]} == {"a" * 32, "b" * 32}

    from lib.rag.db import remove_document

    remove_document(corpus, md5="a" * 32, force=True)
    remove_document(corpus, md5="b" * 32, force=True)
    imported = curate.import_docs(corpus, out_path, hash_embed)
    assert imported["imported"] == 2
    from lib.rag.db import list_documents

    assert {doc["md5"] for doc in list_documents(corpus)} == {"a" * 32, "b" * 32}
    again = curate.import_docs(corpus, out_path, hash_embed)
    assert again["imported"] == 0, "re-import must skip existing md5 keys"

    from lib.rag.db import list_pending_pins

    assert {pin["md5"] for pin in list_pending_pins(corpus)} == {"f" * 32}, (
        "export/import round-trip must preserve pending pins"
    )


def test_curate_prune_pending_clears_queue(corpus):
    pruned = curate.prune_pending(corpus)
    assert pruned["pruned"] == 1
    assert curate.prune_pending(corpus)["pruned"] == 0


def test_curate_remove_respects_guard_and_force(corpus):
    _ingest(corpus, "c" * 32, "Guarded Doc", "guarded corpus text")
    outcome = curate.remove(corpus, "c" * 32)
    assert outcome["removed"] is True


def test_reindex_rebuilds_all_documents(corpus):
    _ingest(corpus, "d" * 32, "Reindex Me", "reindex corpus text one")
    _ingest(corpus, "e" * 32, "Reindex Too", "reindex corpus text two")

    class FixedEmbedder:
        model_name = "fixed-test-model"

        def encode(self, texts):
            return hash_embed(texts)

    report = reindex.reindex(corpus, FixedEmbedder())
    assert report["reindexed"] == 2
    assert report["failures"] == []
    from lib.rag.db import get_meta

    assert get_meta(corpus, "embed_model") == "fixed-test-model"


def test_eval_rag_metrics_and_cli_gate(tmp_path, corpus):
    _ingest(corpus, "1" * 31 + "a", "Quantum Error Correction", "surface codes tolerate depolarizing noise")
    _ingest(corpus, "2" * 31 + "b", "Maritime Signal Intelligence", "direction finding used HF radio bearings")
    golden = [
        {"question": "surface codes depolarizing", "md5": "1" * 31 + "a"},
        {"question": "HF radio bearings", "md5": "2" * 31 + "b"},
    ]
    report = eval_rag.evaluate(corpus, golden, hash_embed, mode="hybrid", k=2)
    assert report["queries"] == 2
    assert report["ndcg"] == pytest.approx(1.0)
    assert report["mrr"] == pytest.approx(1.0)
    assert report["recall"] == pytest.approx(1.0)
    assert report["misses"] == []
    assert report["ndcg_ci"]["low"] <= report["ndcg_ci"]["high"]

    golden_path = tmp_path / "golden.json"
    golden_path.write_text(json.dumps(golden), encoding="utf-8")
    db_path = tmp_path / "rag.sqlite3"
    exit_code = eval_rag.main(["--golden", str(golden_path), "--db", str(db_path), "--mode", "hybrid", "--k", "2"])
    assert exit_code == 0
    strict = eval_rag.main(
        [
            "--golden",
            str(golden_path),
            "--db",
            str(db_path),
            "--mode",
            "hybrid",
            "--k",
            "2",
            "--min-ndcg",
            "1.5",
        ]
    )
    assert strict == 1


def test_golden_coverage_reports_missing_docs(corpus, tmp_path):
    _ingest(corpus, "9" * 32, "Present Doc", "present corpus text")
    golden = [
        {"question": "present", "md5": "9" * 32},
        {"question": "absent", "md5": "8" * 32},
    ]
    report = golden_coverage.coverage(corpus, golden)
    assert report["covered"] == 1
    assert report["missing"] == [{"question": "absent", "md5": "8" * 32, "status": "missing"}]
    statuses = {entry["status"] for entry in report["per_query"]}
    assert statuses == {"covered", "missing"}

    golden_path = tmp_path / "golden.json"
    golden_path.write_text(json.dumps(golden), encoding="utf-8")
    db_file = corpus.execute("PRAGMA database_list").fetchone()[2]
    assert golden_coverage.main(["--golden", str(golden_path), "--db", str(db_file)]) == 0
