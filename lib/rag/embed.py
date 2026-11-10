"""Embedding: fastembed by default, hash-derived vectors for tests and offline use."""
from __future__ import annotations

import hashlib
import re
import struct
import threading
from collections.abc import Sequence

from lib.rag.db import EMBED_DIM

MODEL_NAME = "BAAI/bge-small-en-v1.5"

class Embedder:
    """Structural type: anything with .encode(texts) and .model_name."""

    model_name: str

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class _FunctionEmbedder:
    """Adapter so plain functions like hash_embed satisfy the Embedder interface."""

    model_name = "hash-embed"

    def __init__(self, function):
        self._function = function

    def encode(self, texts):
        return self._function(texts)


def as_embedder(embedder):
    """Wrap a bare encode function; pass-through for objects exposing .encode."""
    if callable(embedder) and not hasattr(embedder, "encode"):
        return _FunctionEmbedder(embedder)
    return embedder


class EmbedderUnavailable(RuntimeError):
    """fastembed is not installed or could not load its model."""

class FastEmbedder:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self._model = None
    def _load(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as error:
                raise EmbedderUnavailable("fastembed is not installed; install the [rag] extra.") from error
            try:
                self._model = TextEmbedding(model_name=self.model_name)
            except Exception as error:
                raise EmbedderUnavailable(f"fastembed model load failed: {error}") from error
        return self._model
    @property
    def dim(self) -> int:
        return EMBED_DIM
    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._load()
        vectors = [[float(value) for value in vector] for vector in model.embed(list(texts))]
        for vector in vectors:
            norm = sum(value * value for value in vector) ** 0.5
            if norm > 0:
                vector[:] = [value / norm for value in vector]
        return vectors

_default: FastEmbedder | None = None
_DEFAULT_LOCK = threading.Lock()

def default_embedder() -> FastEmbedder:
    """Process-wide singleton; the lock keeps concurrent first searches from
    each triggering a model download."""
    global _default
    if _default is None:
        with _DEFAULT_LOCK:
            if _default is None:
                _default = FastEmbedder()
    return _default

def hash_embed(texts: Sequence[str]) -> list[list[float]]:
    """Deterministic token-averaged 384-dim unit vectors; used by tests, never hits the network.
    Each token contributes a unit vector derived from sha256(token), so shared vocabulary
    yields cosine similarity without any model download.
    """
    vectors: list[list[float]] = []
    for text in texts:
        accumulator = [0.0] * EMBED_DIM
        tokens = [token for token in re.findall(r"[a-z0-9]+", str(text).lower()) if token]
        if not tokens:
            tokens = ["empty"]
        for token in tokens:
            seed = hashlib.sha256(token.encode("utf-8")).digest()
            values: list[float] = []
            counter = 0
            while len(values) < EMBED_DIM:
                digest = hashlib.sha256(seed + struct.pack(">I", counter)).digest()
                values.extend((byte / 255.0) * 2 - 1 for byte in digest)
                counter += 1
            norm = sum(value * value for value in values) ** 0.5 or 1.0
            for dimension, value in enumerate(values[:EMBED_DIM]):
                accumulator[dimension] += value / norm
        total = sum(value * value for value in accumulator) ** 0.5 or 1.0
        vectors.append([value / total for value in accumulator])
    return vectors


def get_embedder() -> FastEmbedder:
    """Default production embedder; tests inject hash_embed instead."""
    return default_embedder()
