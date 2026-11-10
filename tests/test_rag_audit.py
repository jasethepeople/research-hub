"""Part-2 audit: behaviours that were never reviewed get direct tests here."""

import time
from datetime import UTC, datetime

import pytest

from lib.rag import db as rag_db
from lib.rag import guard
from lib.rag.embed import hash_embed
from lib.rag.errors import ShrinkBlocked
from lib.rag.retrieve import RRF_K, _reciprocal_rank_fusion, search
from lib.rag.tools import eval_rag, reindex


def test_wal_mode_is_set(tmp_path):
    connection = rag_db.connect(tmp_path / "rag.sqlite3")
    assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_sqlite_vec_is_loaded(tmp_path):
    connection = rag_db.connect(tmp_path / "rag.sqlite3")
    version = connection.execute("SELECT vec_version()").fetchone()[0]
    assert version


def test_vec0_dims_match_embed_dim(tmp_path):
    connection = rag_db.connect(tmp_path / "rag.sqlite3")
    rag_db.initialize(connection)
    with pytest.raises(ValueError):
        rag_db.add_document(
            connection,
            md5="a" * 32,
            title="bad dims",
            source="fixture",
            text="text",
            n_pages=1,
            chunks=["chunk"],
            embeddings=[[0.1] * 383],
        )


def test_updating_a_chunk_reindexes_fts(corpus):
    identifier = rag_db.doc_id_for("m" * 31 + "2")
    corpus.execute("UPDATE chunks SET text = 'unfindable zebra quartet' WHERE doc_id = ?", (identifier,))
    corpus.commit()
    assert search(corpus, "zebra quartet", mode="bm25")
    assert search(corpus, "radio bearings", mode="bm25") == []


def test_removing_a_document_removes_its_vectors(corpus):
    before = corpus.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
    assert before == 3
    rag_db.remove_document(corpus, md5="m" * 31 + "3")
    after = corpus.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0]
    assert after == before - 1
    hits = search(corpus, "posterior updates sensor grid", mode="vector", embedder=hash_embed)
    assert all(hit["md5"] != "m" * 31 + "3" for hit in hits)


def test_rrf_fusion_uses_k_60():
    hit_a = {"chunk_id": 1, "score": 1.0}
    hit_b = {"chunk_id": 2, "score": 0.5}
    fused = _reciprocal_rank_fusion([[hit_a, hit_b], [hit_b, hit_a]], limit=2)
    scores = {hit["chunk_id"]: hit["score"] for hit in fused}
    assert scores[1] == pytest.approx(1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 2))
    assert scores[2] == pytest.approx(scores[1])


def test_doc_ids_scope_limits_results_to_the_requested_docs(corpus):
    scoped = search(
        corpus,
        "bearings",
        mode="bm25",
        doc_ids=["m" * 31 + "2"],
    )
    assert scoped and all(hit["md5"] == "m" * 31 + "2" for hit in scoped)
    empty = search(corpus, "bearings", mode="bm25", doc_ids=["f" * 32])
    assert empty == []
    by_doc_id = search(corpus, "bearings", mode="bm25", doc_ids=[rag_db.doc_id_for("m" * 31 + "2")])
    assert by_doc_id and all(hit["md5"] == "m" * 31 + "2" for hit in by_doc_id)


def test_failed_ingest_never_enters_searchable_corpus(tmp_path):
    connection = rag_db.connect(tmp_path / "rag.sqlite3")
    rag_db.initialize(connection)
    rag_db.add_document(
        connection,
        md5="b" * 32,
        title="empty doc",
        source="fixture",
        text="   ",
        n_pages=1,
        chunks=[],
        embeddings=[],
    )
    for mode in ("vector", "bm25", "hybrid"):
        hits = search(connection, "anything", mode=mode, embedder=hash_embed)
        assert hits == []


def test_shrink_blocked_message_carries_numbers(corpus):
    guard.record_ingest(corpus, docs=1)
    with pytest.raises(ShrinkBlocked) as caught:
        guard.check_shrink(corpus, 5)
    message = str(caught.value)
    assert "5" in message and "1" in message


def test_guard_passes_under_baseline_and_ignores_stale_history(tmp_path):
    import lib.rag.db as rag_db

    connection = rag_db.connect(tmp_path / "guard.sqlite3")
    rag_db.initialize(connection)
    now = time.time()
    guard.record_ingest(connection, docs=2, now=now)
    guard.check_shrink(connection, 2, now=now)
    stale_day = datetime.fromtimestamp(now - 3 * 86_400, UTC).strftime("%Y-%m-%d")
    with connection:
        connection.execute(
            "INSERT INTO corpus_daily (day, docs, bytes) VALUES (?, 50, 0) "
            "ON CONFLICT(day) DO UPDATE SET docs = 50",
            (stale_day,),
        )
    assert guard.baseline_24h(connection, now) == 2
    with pytest.raises(ShrinkBlocked):
        guard.check_shrink(connection, 3, now=now)
    guard.check_shrink(connection, 3, force=True, now=now)
    connection.close()


def test_eval_metric_math_on_hand_computed_fixture():
    ranked = ["a", "b", "c", "d"]
    assert eval_rag._ndcg(ranked, {"b"}, 4) == pytest.approx(0.6309297535714575)
    assert eval_rag._ndcg(["b", "a"], {"a", "b"}, 2) == pytest.approx(1.0)
    assert eval_rag._mrr(ranked, {"c"}) == pytest.approx(1.0 / 3.0)
    assert eval_rag._mrr(ranked, {"z"}) == 0.0
    assert eval_rag._recall(ranked, {"a", "d"}, 4) == pytest.approx(1.0)
    assert eval_rag._recall(ranked, {"a", "z"}, 4) == pytest.approx(0.5)


def test_reindex_is_resumable_and_idempotent_and_neutral_to_daily_counts(corpus):
    docs_before = rag_db.list_documents(corpus)
    daily_before = corpus.execute("SELECT docs FROM corpus_daily ORDER BY day").fetchall()

    class ExplodingEmbedder:
        model_name = "exploder"

        def encode(self, texts):
            raise RuntimeError("boom")

    partial = reindex.reindex(corpus, ExplodingEmbedder())
    assert partial["failures"] and len(partial["failures"]) == len(docs_before)
    assert rag_db.list_documents(corpus) == docs_before, "failed reindex must not touch documents"

    class FixedEmbedder:
        model_name = "fixed-test-model"

        def encode(self, texts):
            return hash_embed(texts)

    first = reindex.reindex(corpus, FixedEmbedder())
    assert first["reindexed"] == len(docs_before) and first["failures"] == []
    chunks_first = {doc["md5"]: doc["n_chunks"] for doc in rag_db.list_documents(corpus)}
    second = reindex.reindex(corpus, FixedEmbedder())
    assert second["reindexed"] == len(docs_before)
    chunks_second = {doc["md5"]: doc["n_chunks"] for doc in rag_db.list_documents(corpus)}
    assert chunks_second == chunks_first

    daily_after = corpus.execute("SELECT docs FROM corpus_daily ORDER BY day").fetchall()
    assert [row[0] for row in daily_after] == [row[0] for row in daily_before]


def test_chunks_span_page_breaks_and_carry_start_pages(tmp_path):
    from lib.rag.ingest import _chunk_with_pages

    page_one = "Alpha fact one. " * 160 + "The boundary fact begins here and"
    page_two = " continues onto the next page without pause. " + "Beta detail sentence. " * 60
    text = page_one + "\n\n" + page_two
    chunks, pages, page_ends = _chunk_with_pages(text, [page_one, page_two])
    assert len(chunks) == len(pages) == len(page_ends) >= 2
    spanning = [chunk for chunk in chunks if "begins here" in chunk and "next page" in chunk]
    assert spanning, "a window must be able to span the page break"
    assert pages[0] == 1
    assert max(page_ends) == 2, "a spanning chunk must record its end page"
    for start, end in zip(pages, page_ends, strict=False):
        assert end is not None and end >= start


def test_citation_page_rendering_tolerates_null():
    from lib.rag.answer import format_citation_pages

    assert format_citation_pages(12, 12) == "p. 12"
    assert format_citation_pages(12, 13) == "pp. 12\u201313"
    assert format_citation_pages(None, None) == ""
    assert format_citation_pages(None, 5) == ""
    label = format_citation_pages(None)
    assert "None" not in label and label == ""
