"""Regression: theme and vocabulary changes must refresh an open PDF.

``window.doc`` used to be a plain attribute that was never assigned by the real load path, so
both refreshes were silently skipped.
"""

from types import SimpleNamespace

from immersion_app.gui.main_window import UnifiedSentenceMinerWindow


def _window(doc):
    window = UnifiedSentenceMinerWindow.__new__(UnifiedSentenceMinerWindow)
    calls = []
    window.pdf_service = SimpleNamespace(doc=doc)
    window.pdf_controller = SimpleNamespace(
        refresh_word_highlights=lambda: calls.append("words"),
        render_current_page=lambda: calls.append("render"),
        page_words=[], page_word_order=[], page_word_index={}, page_line_words={},
        current_page_index=0, zoom_factor=2.0,
    )
    window.current_pdf_path = "book.pdf"
    window.analytics_vocabulary = set()
    window.subtitle_label = SimpleNamespace(set_vocabulary_seen=lambda *_: None)
    return window, calls


def test_doc_property_reflects_pdf_service():
    doc = object()
    window, _ = _window(doc)
    assert window.doc is doc
    window.pdf_service.doc = None
    assert window.doc is None


def test_vocabulary_refresh_updates_highlights_when_pdf_open():
    window, calls = _window(doc=object())
    window._refresh_word_highlights()
    assert calls == ["words"]  # overlay only, no re-raster


def test_vocabulary_refresh_skips_when_no_pdf_open():
    window, calls = _window(doc=None)
    window._refresh_word_highlights()
    assert calls == []


def test_theme_refresh_rerenders_open_pdf():
    window, calls = _window(doc=object())
    window.setStyleSheet = lambda *_: None
    window.queue_dialog = None
    window._render_current_page = lambda: calls.append("render")
    UnifiedSentenceMinerWindow._apply_theme(window, refresh_pdf=True)
    assert "render" in calls
