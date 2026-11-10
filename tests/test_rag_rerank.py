import pytest

from lib.rag.rerank import (
    BLEND,
    CrossEncoderReranker,
    LazyReranker,
    LexicalReranker,
    blend_scores,
    get_reranker,
    rerank_texts,
)


class _FakeCrossEncoder:
    """Stands in for fastembed's TextCrossEncoder and counts inference passes."""

    calls: list[tuple[str, int]] = []

    def __init__(self, model_name=None):
        self.model_name = model_name

    def rerank(self, query, texts):
        type(self).calls.append((query, len(list(texts))))
        return [float(len(set(query.split()) & set(text.split()))) for text in texts]


@pytest.fixture
def fake_cross_encoder(monkeypatch):
    _FakeCrossEncoder.calls = []
    module = __import__("fastembed.rerank.cross_encoder", fromlist=["TextCrossEncoder"])
    monkeypatch.setattr(module, "TextCrossEncoder", _FakeCrossEncoder)
    return _FakeCrossEncoder


def test_rerank_texts_batches_into_one_inference_pass(fake_cross_encoder):
    reranker = CrossEncoderReranker()
    texts = ["alpha beta", "beta gamma", "delta"]
    scores = rerank_texts("alpha beta", texts, reranker)
    assert scores == [2.0, 1.0, 0.0]
    assert fake_cross_encoder.calls == [("alpha beta", 3)], "score_many must issue one rerank call"


def test_score_single_still_works(fake_cross_encoder):
    reranker = CrossEncoderReranker()
    assert reranker.score("alpha beta", "alpha beta gamma") == 2.0


def test_lexical_reranker_score_many_matches_score():
    reranker = LexicalReranker()
    texts = ["alpha beta", "gamma delta", "beta"]
    many = reranker.score_many("alpha beta", texts)
    assert many == [reranker.score("alpha beta", text) for text in texts]


def test_rerank_disable_forces_lexical(monkeypatch):
    monkeypatch.setenv("RERANK_DISABLE", "1")
    assert isinstance(get_reranker(), LexicalReranker)


def test_lazy_reranker_defers_model_load_and_falls_back(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("cross-encoder must not be constructed at get_reranker() time")

    module = __import__("lib.rag.rerank", fromlist=["CrossEncoderReranker"])
    monkeypatch.setattr(module, "CrossEncoderReranker", explode)
    lazy = get_reranker()
    assert isinstance(lazy, LazyReranker)
    score = lazy.score("alpha beta", "alpha beta gamma")
    assert score == pytest.approx(LexicalReranker().score("alpha beta", "alpha beta gamma"))
    assert lazy._delegate is not None and not isinstance(lazy._delegate, CrossEncoderReranker)


def test_lazy_reranker_caches_resolution(fake_cross_encoder):
    lazy = LazyReranker()
    first = lazy.score_many("alpha", ["alpha beta"])
    second = lazy.score("alpha", "alpha beta")
    assert first == [1.0] and second == 1.0
    assert lazy._delegate is fake_cross_encoder or isinstance(lazy._delegate, CrossEncoderReranker)
    assert fake_cross_encoder.calls and len(fake_cross_encoder.calls) == 2


def test_rerank_texts_uses_score_many_when_available(fake_cross_encoder):
    scores = rerank_texts("alpha", ["alpha one", "two"], get_reranker())
    assert scores == [1.0, 0.0]
    assert len(fake_cross_encoder.calls) == 1


def test_blend_weight_unchanged():
    assert BLEND == 0.7
    assert blend_scores(1.0, 0.0) == pytest.approx(0.7)
    assert blend_scores(0.0, 1.0) == pytest.approx(0.3)


@pytest.fixture(autouse=True)
def _fresh_reranker_singleton():
    from lib.rag import rerank

    rerank.reset_reranker_singleton()
    yield
    rerank.reset_reranker_singleton()
