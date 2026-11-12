"""Lexical reranker with optional cross-encoder, plus the hybrid blend."""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Sequence

BLEND = 0.7

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


class LexicalReranker:
    """Token-overlap reranker used when no cross-encoder model is available."""

    def score(self, query: str, text: str) -> float:
        query_tokens = _tokens(query)
        if not query_tokens:
            return 0.0
        text_tokens = _tokens(text)
        if not text_tokens:
            return 0.0
        overlap = len(query_tokens & text_tokens)
        if not overlap:
            return 0.0
        precision = overlap / len(text_tokens)
        recall = overlap / len(query_tokens)
        return 2 * precision * recall / (precision + recall)

    def score_many(self, query: str, texts: Sequence[str]) -> list[float]:
        return [self.score(query, text) for text in texts]


class CrossEncoderReranker:
    """fastembed cross-encoder; the model downloads on first use."""

    def __init__(self, model: str = "Xenova/ms-marco-MiniLM-L-6-v2"):
        self.model = model
        self._model = None

    def _instance(self):
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(model_name=self.model)
        return self._model

    def score_many(self, query: str, texts: Sequence[str]) -> list[float]:
        """One inference pass for the whole batch."""
        if not texts:
            return []
        instance = self._instance()
        return [float(value) for value in instance.rerank(query, list(texts))]

    def score(self, query: str, text: str) -> float:
        scores = self.score_many(query, [text])
        return scores[0] if scores else 0.0


class LazyReranker:
    """Defers cross-encoder loading until the first score call.

    get_reranker() used to instantiate the cross-encoder to probe it, which
    downloaded the model mid-request on first search. This wrapper pays that
    cost on first use instead, caches the resolution, and falls back to the
    lexical reranker if the cross-encoder cannot load or score.
    """

    def __init__(self) -> None:
        self._delegate: LexicalReranker | CrossEncoderReranker | None = None

    def score_many(self, query: str, texts: Sequence[str]) -> list[float]:
        if self._delegate is None:
            try:
                candidate = CrossEncoderReranker()
                scores = candidate.score_many(query, texts)
                self._delegate = candidate
                return scores
            except Exception:  # noqa: BLE001 - any model failure falls back
                self._delegate = LexicalReranker()
        return self._delegate.score_many(query, texts)

    def score(self, query: str, text: str) -> float:
        scores = self.score_many(query, [text])
        return scores[0] if scores else 0.0


_SINGLETON: LazyReranker | LexicalReranker | None = None
_SINGLETON_LOCK = threading.Lock()

def get_reranker():
    """Cheap, lazy reranker factory: no model is touched until first score.

    The resolved reranker is a process-wide singleton (behind a lock) so the
    cross-encoder loads exactly once per process even under concurrent first
    searches; RERANK_DISABLE=1 forces the lexical reranker.
    """
    global _SINGLETON
    if os.environ.get("RERANK_DISABLE") == "1":
        return LexicalReranker()
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = LazyReranker()
    return _SINGLETON


def rerank_texts(query: str, texts: Sequence[str], reranker=None) -> list[float]:
    reranker = reranker or get_reranker()
    if hasattr(reranker, "score_many"):
        return [float(value) for value in reranker.score_many(query, texts)]
    return [float(reranker.score(query, text)) for text in texts]


def blend_scores(rerank_score: float, retrieval_score: float) -> float:
    """Final score: BLEND weight on the reranker, the rest on retrieval rank."""
    return BLEND * rerank_score + (1.0 - BLEND) * retrieval_score


def reset_reranker_singleton() -> None:
    """Test hook: drop the process-wide reranker so the next get_reranker() re-resolves."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None
