import pytest

from lib.rag.errors import ScannedDoc, UnsupportedFormat
from lib.rag.extract import extract_djvu, extract_epub, extract_pdf, extract_text, extract_txt

fitz = pytest.importorskip("fitz")
pytest.importorskip("ebooklib")


def _write_text_pdf(tmp_path, pages=2):
    document = fitz.open()
    for index in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {index} discusses signal processing in depth.")
    path = tmp_path / "text.pdf"
    document.save(str(path))
    document.close()
    return path


def _write_scanned_pdf(tmp_path):
    document = fitz.open()
    page = document.new_page()
    pix = page.get_pixmap(dpi=72)
    pix.save(str(tmp_path / "only_image.png"))
    path = tmp_path / "scanned.pdf"
    document.save(str(path))
    document.close()
    return path


def test_extract_pdf_returns_text_and_pages(tmp_path):
    outcome = extract_pdf(_write_text_pdf(tmp_path))
    assert outcome["n_pages"] == 2
    assert "signal processing" in outcome["text"]


def test_extract_pdf_flags_scanned_document(tmp_path):
    with pytest.raises(ScannedDoc):
        extract_pdf(_write_scanned_pdf(tmp_path))


def test_extract_txt(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("plain notes", encoding="utf-8")
    assert extract_txt(path)["text"] == "plain notes"


def test_extract_text_dispatches_by_suffix(tmp_path):
    path = _write_text_pdf(tmp_path)
    assert "signal processing" in extract_text(path)["text"]


def test_extract_epub(tmp_path):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("fixture-epub")
    book.set_title("Fixture")
    chapter = epub.EpubHtml(title="One", file_name="one.xhtml", lang="en")
    chapter.content = "<html><body><p>epub body text</p></body></html>"
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [chapter]
    path = tmp_path / "book.epub"
    epub.write_epub(str(path), book)
    outcome = extract_epub(path)
    assert "epub body text" in outcome["text"]


def test_extract_djvu_without_tool_is_unsupported(tmp_path, monkeypatch):
    import shutil

    path = tmp_path / "doc.djvu"
    path.write_bytes(b"AT&FORM=DJVU")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(UnsupportedFormat):
        extract_djvu(path)
