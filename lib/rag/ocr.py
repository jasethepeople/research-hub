"""Tesseract OCR for scanned PDFs, with a JSON cache keyed by file digest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from lib.rag.errors import OcrUnavailable

DPI = 300
MIN_CONFIDENCE = 60


def _require_tesseract() -> None:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
    except Exception as error:  # pytesseract raises TesseractNotFoundError (an OSError subclass)
        raise OcrUnavailable(f"tesseract is unavailable: {error.__class__.__name__}") from error


def cache_path(path: Path, cache_dir: Path) -> Path:
    digest = hashlib.sha1(Path(path).read_bytes()).hexdigest()
    return cache_dir / f"{digest}.json"


def _page_text(image, min_confidence: int) -> str:
    import pytesseract

    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words: list[str] = []
    for token, confidence in zip(data["text"], data["conf"], strict=True):
        try:
            score = float(confidence)
        except (TypeError, ValueError):
            continue
        if score >= min_confidence and token.strip():
            words.append(token.strip())
    return " ".join(words)


def ocr_pdf(
    path: Path,
    *,
    dpi: int = DPI,
    min_confidence: int = MIN_CONFIDENCE,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    _require_tesseract()
    import io

    import fitz
    from PIL import Image

    if cache_dir is not None:
        cached = cache_path(path, cache_dir)
        if cached.is_file():
            payload = json.loads(cached.read_text(encoding="utf-8"))
            if payload.get("dpi") == dpi:
                return payload

    document = fitz.open(path)
    try:
        pages: list[str] = []
        for page in document:
            pixmap = page.get_pixmap(dpi=dpi)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            pages.append(_page_text(image, min_confidence))
        n_pages = document.page_count
    finally:
        document.close()

    payload = {"text": "\n\n".join(pages), "n_pages": n_pages, "format": "pdf-ocr", "dpi": dpi}
    if cache_dir is not None:
        payload["cache_path"] = str(cache_path(path, cache_dir))
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path(path, cache_dir).write_text(json.dumps(payload), encoding="utf-8")
    return payload