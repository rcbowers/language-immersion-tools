"""PDFService behaviour for reflowable EPUB documents (synthetic EPUB, real PyMuPDF)."""

from __future__ import annotations

import pymupdf

from immersion_app.core.pdf_service import (
    EPUB_FONT_SIZE,
    EPUB_PAGE_HEIGHT,
    EPUB_PAGE_WIDTH,
    PDFService,
    doc_kind_for_path,
)


def _make_pdf(path, text="hola"):
    doc = pymupdf.open()
    doc.new_page().insert_text((40, 60), text, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def test_doc_kind_follows_suffix():
    assert doc_kind_for_path("C:/books/Libro.EPUB") == "epub"
    assert doc_kind_for_path("C:/books/libro.pdf") == "pdf"
    assert doc_kind_for_path("") == "pdf"


def test_load_lays_out_epub_on_fixed_size_pages(qapp, make_epub):
    service = PDFService()
    doc = service.load_document(str(make_epub()))

    assert service.doc_kind == "epub"
    assert service.is_reflowable
    assert doc.page_count > 2
    assert service.page_size(0) == (EPUB_PAGE_WIDTH, EPUB_PAGE_HEIGHT)
    service.close_document()
    assert not service.is_reflowable


def test_pdf_is_not_reflowable(qapp, tmp_path):
    service = PDFService()
    service.load_document(str(_make_pdf(tmp_path / "a.pdf")))

    assert service.doc_kind == "pdf"
    assert not service.is_reflowable
    assert service.location_for_page(0) is None
    assert service.page_for_location(0, 0) is None


def test_render_page_extracts_words(qapp, make_epub):
    service = PDFService()
    service.load_document(str(make_epub()))

    result = service.render_page(0, 1.0)

    assert result is not None and result.words
    assert "Capitulo" in {w[4] for w in result.words}
    assert result.line_map


def test_toc_lists_chapters_with_zero_based_pages(qapp, make_epub):
    service = PDFService()
    service.load_document(str(make_epub(chapters=3)))

    toc = service.get_toc()

    assert [(level, title) for level, title, _ in toc] == [(1, "Capitulo 1"), (1, "Capitulo 2"), (1, "Capitulo 3")]
    assert toc[0][2] == 0
    assert toc[0][2] < toc[1][2] < toc[2][2]


def test_location_round_trips_through_a_fresh_load(qapp, make_epub):
    path = str(make_epub())
    first = PDFService()
    first.load_document(path)
    target = first.page_count() - 2
    location = first.location_for_page(target)
    assert location is not None

    second = PDFService()
    second.load_document(path)

    assert second.page_for_location(*location) == target


def test_page_for_location_rejects_out_of_range(qapp, make_epub):
    service = PDFService()
    service.load_document(str(make_epub()))

    assert service.page_for_location(99, 99) is None


def test_reflowable_context_is_the_full_sentence(qapp, make_epub):
    service = PDFService()
    service.load_document(str(make_epub(chapters=1, paragraphs=5)))
    result = service.render_page(0, 1.0)
    word = next(w for w in result.words if w[4] == "esto")

    context = service.extract_context([word], result.line_map)

    assert context.startswith("Hola mundo, esto es la frase")
    assert context.endswith(".")


def test_pdf_context_stays_one_line(qapp, tmp_path):
    service = PDFService()
    service.load_document(str(_make_pdf(tmp_path / "a.pdf", "Hola mundo. Otra frase")))
    result = service.render_page(0, 1.0)

    assert service.extract_context([result.words[0]], result.line_map) == "Hola mundo. Otra frase"


def test_layout_constants_are_sane():
    assert EPUB_PAGE_WIDTH > 0 and EPUB_PAGE_HEIGHT > EPUB_PAGE_WIDTH and EPUB_FONT_SIZE > 0
