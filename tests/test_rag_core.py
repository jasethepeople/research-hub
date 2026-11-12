"""Offline tests for the RAG core: schema, chunking, retrieval, guard, gate."""


import json
import time
from datetime import UTC, datetime

import pytest

from lib.rag import available, gate, guard
from lib.rag import db as rag_db
from lib.rag.chunk import chunk_text
from lib.rag.embed import hash_embed
from lib.rag.errors import EmbedMismatch, EvalLocked, ShrinkBlocked
from lib.rag.retrieve import search

pytestmark = pytest.mark.skipif(not available(), reason="rag extras not installed")

DOCS = [
    ("m" * 31 + "1", "Quantum Error Correction", "surface codes tolerate depolarizing noise"),
    ("m" * 31 + "2", "Maritime Signal Intelligence", "direction finding used HF radio bearings"),
    ("m" * 31 + "3", "Bayesian Sensor Networks", "posterior updates across the sensor grid"),
]



def test_schema_tables_exist(corpus):
    names = {
        row[0]
        for row in corpus.execute("SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')").fetchall()
    }
    # virtual tables are type "table" in sqlite_master
    expected = {"meta", "corpus", "chunks", "chunks_fts", "vec_chunks", "corpus_daily", "pending_pins"}
    assert expected <= names


def test_doc_id_is_sha1_of_md5_truncated(corpus):
    import hashlib

    identifier = rag_db.doc_id_for("m" * 31 + "1")
    assert identifier == hashlib.sha1(("m" * 31 + "1").encode()).hexdigest()[:16]
    row = corpus.execute("SELECT doc_id FROM corpus WHERE md5 = ?", ("m" * 31 + "1",)).fetchone()
    assert row[0] == identifier


def test_fts_triggers_stay_in_sync(corpus):
    hits = search(corpus, "depolarizing", mode="bm25")
    assert hits and hits[0]["doc_id"] == rag_db.doc_id_for("m" * 31 + "1")
    rag_db.remove_document(corpus, md5="m" * 31 + "1")
    assert search(corpus, "depolarizing", mode="bm25") == []
    assert corpus.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == 2


def test_chunk_text_overlap_is_stable():
    text = " ".join(f"sentence {index} about signal processing" for index in range(80))
    chunks = chunk_text(text, size=200, overlap=50)
    assert len(chunks) > 1
    assert all(len(chunk) <= 240 for chunk in chunks)
    assert chunks[0][-50:].strip() in chunks[1]


def test_embed_mismatch_on_model_change(corpus):
    rag_db.set_model(corpus, "test-model", 384)
    with pytest.raises(EmbedMismatch):
        rag_db.assert_model(corpus, "other-model", 384)
    rag_db.assert_model(corpus, "test-model", 384)


def test_vector_retrieve_matches_expected_doc(corpus):
    hits = search(corpus, "surface codes tolerate depolarizing noise", mode="vector", limit=1, embedder=hash_embed)
    assert hits[0]["doc_id"] == rag_db.doc_id_for("m" * 31 + "1")


def test_hybrid_fuses_vector_and_bm25(corpus):
    hits = search(corpus, "radio bearings", mode="hybrid", limit=3, embedder=hash_embed)
    assert hits[0]["doc_id"] == rag_db.doc_id_for("m" * 31 + "2")
    reranked = search(corpus, "radio bearings", mode="hybrid_rerank", limit=3, embedder=hash_embed)
    assert reranked[0]["doc_id"] == rag_db.doc_id_for("m" * 31 + "2")


def test_empty_corpus_returns_no_hits(tmp_path):
    connection = rag_db.connect(tmp_path / "empty.sqlite3")
    rag_db.initialize(connection)
    for mode in ("vector", "bm25", "hybrid", "hybrid_rerank"):
        assert search(connection, "anything", mode=mode, embedder=hash_embed) == []


def test_guard_blocks_shrink_past_24h_baseline(corpus):
    now = 1_700_000_000.0
    guard.record_ingest(corpus, docs=1, bytes_written=10, now=now)
    assert guard.baseline_24h(corpus, now=now) == 1
    guard.check_shrink(corpus, 1, now=now)
    with pytest.raises(ShrinkBlocked):
        guard.check_shrink(corpus, 2, now=now)
    guard.check_shrink(corpus, 5, now=now, force=True)


def test_gate_windows_and_eval_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_STATE", str(tmp_path))
    monkeypatch.setenv("INGEST_WINDOWS", "")
    allowed, _ = gate.can_ingest(now=mktime_utc(12, 0))
    assert allowed
    monkeypatch.setenv("INGEST_WINDOWS", "00:00-23:59")
    allowed, _ = gate.can_ingest(now=mktime_utc(12, 0))
    assert allowed
    monkeypatch.setenv("INGEST_WINDOWS", "23:00-23:30")
    allowed, reason = gate.can_ingest(now=mktime_utc(12, 0))
    assert not allowed and reason

    with gate.eval_lock():
        with pytest.raises(EvalLocked):
            with gate.eval_lock():
                pass

def test_can_ingest_refuses_outside_window(tmp_path, monkeypatch):
    monkeypatch.delenv("INGEST_WINDOWS", raising=False)
    monkeypatch.setenv("HUB_STATE", str(tmp_path))
    noon = datetime(2026, 1, 1, 12, 0, tzinfo=UTC).timestamp()
    allowed, note = gate.can_ingest(now=noon, spec="23:00-23:30")
    assert allowed is False
    assert "23:00-23:30" in note


def test_gate_supports_midnight_wrap_windows(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_STATE", str(tmp_path))
    monkeypatch.setenv("INGEST_WINDOWS", "")
    from lib.rag import gate

    monkeypatch.setenv("INGEST_WINDOWS", "22:00-02:00")
    allowed, _ = gate.can_ingest(now=mktime_utc(23, 30))
    assert allowed, "23:30 must fall inside a 22:00-02:00 window"
    allowed, _ = gate.can_ingest(now=mktime_utc(1, 0))
    assert allowed, "01:00 must fall inside a 22:00-02:00 window"
    allowed, reason = gate.can_ingest(now=mktime_utc(12, 0))
    assert not allowed and "windows" in reason.lower()


def test_gate_override_file_is_honoured_and_expires(tmp_path, monkeypatch):
    from lib.rag import gate

    monkeypatch.setenv("HUB_STATE", str(tmp_path))
    monkeypatch.setenv("INGEST_WINDOWS", "03:00-04:00")
    override = tmp_path / "ingest-override.json"
    now = 1_700_000_000.0
    override.write_text(json.dumps({"until": now + 3600, "reason": "bulk import"}), encoding="utf-8")
    allowed, note = gate.can_ingest(now=now)
    assert allowed and "bulk import" in note

    override.write_text(json.dumps({"until": now - 1, "reason": "stale"}), encoding="utf-8")
    allowed, reason = gate.can_ingest(now=now)
    assert not allowed and reason


def test_guard_passes_under_baseline_and_when_history_is_stale(corpus):
    import time as time_module

    from lib.rag import guard

    now = time_module.time()
    before = guard.baseline_24h(corpus, now)
    guard.record_ingest(corpus, docs=2, now=now)
    assert guard.baseline_24h(corpus, now) == before + 2
    guard.check_shrink(corpus, 2, now=now)

    old = now - 3 * 86_400
    connection = corpus
    day = datetime.fromtimestamp(old, UTC).strftime("%Y-%m-%d")
    with connection:
        connection.execute(
            "INSERT INTO corpus_daily (day, docs, bytes) VALUES (?, 50, 0) ON CONFLICT(day) DO UPDATE SET docs = 50",
            (day,),
        )
    assert guard.baseline_24h(connection, now) == before + 2
    with pytest.raises(ShrinkBlocked):
        guard.check_shrink(connection, before + 3, now=now)
    guard.check_shrink(connection, before + 3, force=True, now=now)


def test_shrink_blocked_carries_the_numbers(corpus):
    from lib.rag import guard

    now = time.time()
    guard.record_ingest(corpus, docs=1, now=now)
    with pytest.raises(ShrinkBlocked) as caught:
        guard.check_shrink(corpus, 5, now=now)
    message = str(caught.value)
    assert "5" in message and "1" in message


def mktime_utc(hour: int, minute: int) -> float:
    return datetime(2024, 1, 15, hour, minute, tzinfo=UTC).timestamp()


MIDNIGHT_WRAP_CASES = [
    ("23:30", 1705361400.0, True),
    ("01:00", 1705280400.0, True),
    ("12:00", 1705320000.0, False),
]


def test_gate_windows_wrap_midnight(monkeypatch):
    monkeypatch.setenv("INGEST_WINDOWS", "22:00-02:00")
    for label, moment, expected in MIDNIGHT_WRAP_CASES:
        allowed, _ = gate.can_ingest(now=moment)
        assert allowed is expected, label


def test_gate_override_file_honoured_and_expires(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_STATE", str(tmp_path))
    monkeypatch.setenv("INGEST_WINDOWS", "03:00-04:00")
    override = tmp_path / "ingest-override.json"
    override.write_text(json.dumps({"until": time.time() + 3600, "reason": "bulk import"}), encoding="utf-8")
    allowed, reason = gate.can_ingest(now=time.time())
    assert allowed and "bulk import" in reason
    expired = tmp_path / "expired.json"
    expired.write_text(json.dumps({"until": 1, "reason": "stale"}), encoding="utf-8")
    active, _ = gate.read_override(now=time.time(), path=expired)
    assert not active
    override.write_text(json.dumps({"until": 1, "reason": "stale"}), encoding="utf-8")
    allowed, _ = gate.can_ingest(now=time.time())
    assert not allowed
