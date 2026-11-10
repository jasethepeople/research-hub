"""Shared RAG exceptions."""

from __future__ import annotations


class RagUnavailable(RuntimeError):
    """The optional [rag] dependency group is missing or incomplete."""


class EmbedMismatch(RuntimeError):
    """Stored corpus vectors do not match the requested embedding model."""


class ScannedDoc(RuntimeError):
    """A document has too little embedded text and needs OCR."""


class OcrUnavailable(RuntimeError):
    """tesseract (or its Python binding) is not installed."""


class ShrinkBlocked(RuntimeError):
    """A deletion was refused because it would shrink the corpus past the 24h baseline."""


class EvalLocked(RuntimeError):
    """The evaluation lock is held by another process."""


class UnsupportedFormat(RuntimeError):
    """The file format has no available extractor."""