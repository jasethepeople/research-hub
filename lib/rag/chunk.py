"""Text chunking: paragraph-aware sliding windows with overlap."""

from __future__ import annotations

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if size <= overlap:
        raise ValueError("size must exceed overlap")
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= size:
        return [cleaned] if cleaned else []
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + size, len(cleaned))
        if end < len(cleaned):
            window = cleaned[start:end]
            cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "), window.rfind("\n"))
            if cut > overlap:
                end = start + cut + 1
        chunk = " ".join(cleaned[start:end].split())
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks