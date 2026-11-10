import pytest

from lib.rag import db as rag_db
from lib.rag.embed import hash_embed
from lib.rag.rerank import BLEND, blend_scores
from lib.rag.retrieve import search


def test_vector_retrieve_matches_expected_doc(corpus):
    hits = search(corpus, "surface codes depolarizing", mode="vector", limit=1, embedder=hash_embed)
    assert hits and hits[0]["title"] == "Quantum Error Correction"


def test_bm25_retrieve_matches_expected_doc(corpus):
    hits = search(corpus, "radio bearings", mode="bm25", limit=1)
    assert hits and hits[0]["title"] == "Maritime Signal Intelligence"


def test_hybrid_fuses_both_channels(corpus):
    hits = search(corpus, "sensor grid posterior", mode="hybrid", limit=3, embedder=hash_embed)
    assert hits
    assert all(hit["score"] > 0 for hit in hits)
    assert hits[0]["title"] == "Bayesian Sensor Networks"


def test_hybrid_rerank_blends_scores_with_fixed_weight(corpus):
    reranked = search(corpus, "posterior sensor grid", mode="hybrid_rerank", limit=3, embedder=hash_embed)
    assert reranked and reranked[0]["title"] == "Bayesian Sensor Networks"
    assert blend_scores(1.0, 0.0) == pytest.approx(BLEND)
    assert blend_scores(0.0, 1.0) == pytest.approx(1.0 - BLEND)


def test_retrieve_empty_corpus_returns_no_hits(tmp_path):
    connection = rag_db.connect(tmp_path / "empty.sqlite3")
    rag_db.initialize(connection)
    assert search(connection, "anything", embedder=hash_embed) == []


def test_rerank_blend_is_deterministic():
    assert blend_scores(0.8, 0.2) == pytest.approx(BLEND * 0.8 + (1 - BLEND) * 0.2)
