import pytest

from lib.rag.errors import OcrUnavailable
from lib.rag.ocr import ocr_pdf

pytest.importorskip("fitz")
pytesseract = pytest.importorskip("pytesseract")


def _tesseract_present() -> bool:
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


def test_ocr_pdf_requires_tesseract(tmp_path, monkeypatch):
    def _missing(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "get_tesseract_version", _missing)
    empty = tmp_path / "empty.pdf"
    import fitz

    document = fitz.open()
    document.new_page()
    document.save(str(empty))
    document.close()
    with pytest.raises(OcrUnavailable):
        ocr_pdf(empty, cache_dir=tmp_path / "cache")


@pytest.mark.skipif(not _tesseract_present(), reason="tesseract binary not installed")
def test_ocr_pdf_reads_scanned_page_and_caches(tmp_path):
    import fitz

    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 100), "OCRed sentence about antennas.", fontsize=24)
    pix = page.get_pixmap(dpi=300)
    pix.save(str(tmp_path / "page.png"))
    scanned = tmp_path / "scanned.pdf"
    document.save(str(scanned))
    document.close()

    outcome = ocr_pdf(scanned, cache_dir=tmp_path / "cache")
    assert outcome["n_pages"] == 1
    assert "antennas" in outcome["text"].lower()

    cached = outcome["cache_path"]
    again = ocr_pdf(scanned, cache_dir=tmp_path / "cache")
    assert again["cache_path"] == cached
    assert again["text"] == outcome["text"]
