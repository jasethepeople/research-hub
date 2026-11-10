"""Text extraction for pdf, epub, djvu, and txt sources."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from lib.rag.errors import ScannedDoc, UnsupportedFormat

SCAN_THRESHOLD = 0.25


def _pages_with_text(pages: list[str]) -> int:
    return sum(1 for page in pages if page.strip())


def extract_pdf(path: Path) -> dict[str, Any]:
    import fitz

    document = fitz.open(path)
    try:
        pages = [page.get_text() or "" for page in document]
        page_count = document.page_count
    finally:
        document.close()
    if page_count and _pages_with_text(pages) / page_count < SCAN_THRESHOLD:
        raise ScannedDoc(f"Only {_pages_with_text(pages)}/{page_count} pages have embedded text.")
    return {"text": "\n\n".join(pages), "n_pages": page_count, "pages": pages, "format": "pdf"}


def extract_epub(path: Path) -> dict[str, Any]:
    import ebooklib
    from bs4 import BeautifulSoup
    from ebooklib import epub

    book = epub.read_epub(str(path))
    parts: list[str] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        if text:
            parts.append(text)
    if not parts:
        raise ScannedDoc("EPUB contained no text documents.")
    return {"text": "\n\n".join(parts), "n_pages": len(parts), "pages": parts, "format": "epub"}


def extract_djvu(path: Path) -> dict[str, Any]:
    binary = shutil.which("djvutxt")
    if binary is None:
        raise UnsupportedFormat("djvutxt is not installed; djvu extraction is unavailable.")
    result = subprocess.run([binary, str(path)], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise UnsupportedFormat(f"djvutxt failed: {result.stderr.strip()[:200]}")
    text = result.stdout
    return {"text": text, "n_pages": 1, "pages": [text], "format": "djvu"}


def extract_txt(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"text": text, "n_pages": 1, "pages": [text], "format": "txt"}


EXTRACTORS = {
    ".pdf": extract_pdf,
    ".epub": extract_epub,
    ".djvu": extract_djvu,
    ".djv": extract_djvu,
    ".txt": extract_txt,
    ".md": extract_txt,
}


def extract_text(path: Path) -> dict[str, Any]:
    extractor = EXTRACTORS.get(Path(path).suffix.lower())
    if extractor is None:
        raise UnsupportedFormat(f"No extractor for {Path(path).suffix.lower()!r} files.")
    return extractor(Path(path))