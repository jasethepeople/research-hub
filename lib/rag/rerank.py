"""Lexical reranker with optional cross-encoder, plus the hybrid blend."""

from __future__ import annotations

import re
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

    def score(self, query: str, text: str) -> float:
        instance = self._instance()
        for value in instance.rerank(query, [text]):
            return float(value)
        return 0.0


def get_reranker():
    try:
        reranker = CrossEncoderReranker()
        reranker._instance()
        return reranker
    except Exception:
        return LexicalReranker()


def rerank_texts(query: str, texts: Sequence[str], reranker=None) -> list[float]:
    reranker = reranker or get_reranker()
    return [float(reranker.score(query, text)) for text in texts]


def blend_scores(rerank_score: float, retrieval_score: float) -> float:
    """Final score: BLEND weight on the reranker, the rest on retrieval rank."""
    return BLEND * rerank_score + (1.0 - BLEND) * retrieval_score