"""PDFController navigation, loading and rendering against a real PDFService and a generated PDF."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import fitz
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor

from immersion_app.core.appearance_manager import AppearanceMode
from immersion_app.core.pdf_service import PDFService
from immersion_app.core.selection_state import SelectionState
from immersion_app.gui.controllers.pdf_controller import PDFController


@pytest.fixture
def sample_pdf(tmp_path):
    path = tmp_path / "libro.pdf"
    doc = fitz.open()
    for i in range(5):
        page = doc.new_page(width=300, height=400)
        page.insert_text((40, 60), f"Página {i + 1}: hola mundo, ¿qué tal?", fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


class _Mining:
    def __init__(self):
        self.cleared = 0
        self.prefetched = []

    def clear_selection(self):
        self.cleared += 1

    def prefetch_translations(self, texts):
        self.prefetched.append(list(texts))

    def request_translation(self, text):
        pass


class _Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _record(*args, **kwargs):
            self.calls.append((name, args))
        return _record


def _make_window(dark=False):
    labels = {}
    window = SimpleNamespace(
        current_pdf_path="",
        current_page_index=0,
        current_source_name="",
        current_source_location="",
        user_data={"recent_files": []},
        appearance_manager=SimpleNamespace(current_mode=AppearanceMode.DARK if dark else AppearanceMode.LIGHT),
        analytics_vocabulary=set(),
        mode_manager=_Recorder(),
        command_bar=_Recorder(),
        pdf_status_bar=_Recorder(),
        usage_tracker=_Recorder(),
        pdf_label=SimpleNamespace(
            setPixmap=lambda pixmap: labels.__setitem__("pixmap", pixmap),
            resize=lambda size: None,
            set_word_highlights=lambda items: labels.__setitem__("words", list(items)),
            set_selection_rects=lambda rects, color=None: labels.setdefault("selections", []).append(list(rects)),
        ),
        scroll_resets=0,
        persists=0,
        _labels=labels,
    )
    window.mode_manager.current_mode = None
    window._clean_word = lambda text: text.strip(".,¿?¡!:").lower()
    window._iter_unique_clean_words = lambda values: list(dict.fromkeys(v for v in (window._clean_word(x) for x in values) if v))
    window._update_source_summary = lambda: None
    window._set_status = lambda *a, **k: None
    window._update_command_bar_stats = lambda: None
    window._close_popover = lambda: None
    window._show_translation_popover = lambda: None
    window._reset_pdf_scroll_position = lambda: setattr(window, "scroll_resets", window.scroll_resets + 1)
    window._persist_session = lambda: setattr(window, "persists", window.persists + 1)
    return window


@pytest.fixture
def controller_factory(qapp):
    def _make(dark=False):
        window = _make_window(dark)
        selection = SelectionState()
        controller = PDFController(window, PDFService(), selection, _Mining())
        return controller, window

    return _make


def _settle(qapp, controller, timeout_s=10.0):
    """Pump the event loop until the controller has applied the pending render."""
    import time

    deadline = time.perf_counter() + timeout_s
    while controller.render_pending and time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(0.001)
    qapp.processEvents()
    assert not controller.render_pending, "render never settled"


def _load(controller, path, page=0):
    with patch("immersion_app.gui.controllers.pdf_controller.QTimer.singleShot") as single_shot, patch(
        "immersion_app.gui.controllers.pdf_controller.save_user_data"
    ):
        controller.load_pdf(str(path), initial_page_index=page)
    return single_shot


def test_load_pdf_restores_page_and_schedules_fit_and_scroll_reset(controller_factory, sample_pdf):
    controller, window = controller_factory()
    single_shot = _load(controller, sample_pdf, page=3)

    assert controller.current_page_index == 3
    assert window.current_page_index == 3
    assert single_shot.call_count == 2  # fit width + scroll reset
    assert window.user_data["recent_files"][0]["page_index"] == 3
    assert ("set_pdf_page_index", (3,)) in window.usage_tracker.calls


def test_load_pdf_clamps_out_of_range_page(controller_factory, sample_pdf):
    controller, _window = controller_factory()
    _load(controller, sample_pdf, page=99)
    assert controller.current_page_index == 4


@pytest.mark.parametrize(
    "action, start, expected",
    [("next_page", 2, 3), ("prev_page", 2, 1), ("next_page", 4, 4), ("prev_page", 0, 0)],
)
def test_page_navigation_resets_scroll_and_records_activity(controller_factory, sample_pdf, action, start, expected):
    controller, window = controller_factory()
    _load(controller, sample_pdf, page=start)
    resets_before, persists_before = window.scroll_resets, window.persists

    getattr(controller, action)()

    assert controller.current_page_index == expected
    moved = expected != start
    assert window.scroll_resets == resets_before + (1 if moved else 0)
    assert window.persists == persists_before + (1 if moved else 0)
    assert (("record_activity", ()) in window.usage_tracker.calls) == moved


def test_jump_to_page_validates_range(controller_factory, sample_pdf):
    controller, window = controller_factory()
    _load(controller, sample_pdf)

    controller.jump_to_page(5)
    assert controller.current_page_index == 4
    controller.jump_to_page(0)
    controller.jump_to_page(6)
    assert controller.current_page_index == 4


def test_render_extracts_words_and_prefetches(controller_factory, sample_pdf, qapp):
    controller, window = controller_factory()
    _load(controller, sample_pdf)

    controller.render_current_page()
    _settle(qapp, controller)

    assert window._labels["pixmap"] is not None
    assert any(word[4].startswith("hola") for word in controller.page_word_order)
    assert "hola" in controller.mining_controller.prefetched[-1]


def test_render_inverts_page_in_dark_mode(controller_factory, sample_pdf, qapp):
    light, _ = controller_factory(dark=False)
    dark, dark_window = controller_factory(dark=True)
    for controller in (light, dark):
        _load(controller, sample_pdf)
        controller.render_current_page()
        _settle(qapp, controller)
    light_pixel = light.window._labels["pixmap"].toImage().pixelColor(5, 5)
    dark_pixel = dark_window._labels["pixmap"].toImage().pixelColor(5, 5)
    assert light_pixel.lightness() > 200  # white paper
    assert dark_pixel.lightness() < 60  # inverted


# --- async rendering, cache and overlay ---------------------------------------------------------


def _first_word_point(controller):
    word = controller.page_word_order[0]
    return QPoint(int((word[0] + word[2]) / 2 * controller.zoom_factor), int((word[1] + word[3]) / 2 * controller.zoom_factor))


def test_render_is_asynchronous_and_keeps_previous_page_until_ready(controller_factory, sample_pdf, qapp):
    controller, window = controller_factory()
    _load(controller, sample_pdf)

    controller.render_current_page()

    assert controller.render_pending
    assert "pixmap" not in window._labels  # nothing painted synchronously
    _settle(qapp, controller)
    assert window._labels["pixmap"] is not None


def test_cached_page_applies_synchronously(controller_factory, sample_pdf, qapp):
    controller, window = controller_factory()
    _load(controller, sample_pdf)
    controller.render_current_page()
    _settle(qapp, controller)
    window._labels.pop("pixmap")

    controller.render_current_page()  # same page/zoom/theme -> cache hit

    assert not controller.render_pending
    assert "pixmap" in window._labels


def test_neighbour_pages_are_prefetched_after_current_page_is_applied(controller_factory, sample_pdf, qapp):
    controller, _window = controller_factory()
    _load(controller, sample_pdf, page=2)
    controller.render_current_page()
    _settle(qapp, controller)
    assert controller.pdf_service.wait_for_renders(10000)
    qapp.processEvents()

    for neighbour in (1, 3):
        assert controller._cache_key(neighbour) in controller._cache
    assert controller._cache_key(0) not in controller._cache

    controller.next_page()  # prefetched -> instant
    assert not controller.render_pending
    assert controller.current_page_index == 3


def test_stale_render_result_is_not_applied(controller_factory, sample_pdf, qapp):
    controller, window = controller_factory()
    _load(controller, sample_pdf, page=0)
    controller.render_current_page()  # request for page 0 ...
    controller.current_page_index = 3
    controller.render_current_page()  # ... superseded by a request for page 3
    _settle(qapp, controller)
    assert controller.pdf_service.wait_for_renders(10000)
    qapp.processEvents()

    assert controller.page_word_order and "Página" in " ".join(w[4] for w in controller.page_word_order)
    assert "4:" in " ".join(w[4] for w in controller.page_word_order)  # page 4 (index 3), not page 1


def test_reset_render_state_drops_cache_and_late_results(controller_factory, sample_pdf, qapp):
    controller, window = controller_factory()
    _load(controller, sample_pdf)
    controller.render_current_page()
    controller.reset_render_state()  # e.g. document closed while a render was in flight
    assert controller.pdf_service.wait_for_renders(10000)
    qapp.processEvents()

    assert not controller.render_pending
    assert len(controller._cache) == 0
    assert "pixmap" not in window._labels


def test_click_moves_overlay_without_rerendering(controller_factory, sample_pdf, qapp):
    controller, window = controller_factory()
    _load(controller, sample_pdf)
    controller.render_current_page()
    _settle(qapp, controller)
    pixmap_before = window._labels["pixmap"]
    renders = []
    original = controller.pdf_service.render_async
    controller.pdf_service.render_async = lambda *a, **k: (renders.append(a), original(*a, **k))[1]

    controller.click_at(_first_word_point(controller), Qt.KeyboardModifier.NoModifier)

    assert not controller.render_pending
    assert renders == []
    assert window._labels["pixmap"] is pixmap_before
    assert window._labels["selections"][-1], "selection rect should be set on the overlay"


def test_word_highlights_cover_words_with_seen_and_new_colours(controller_factory, sample_pdf, qapp):
    controller, window = controller_factory()
    window.analytics_vocabulary = {"hola"}
    _load(controller, sample_pdf)
    controller.render_current_page()
    _settle(qapp, controller)

    items = window._labels["words"]
    assert len(items) == len([w for w in controller.page_words if window._clean_word(w[4])])

    window.analytics_vocabulary = set()
    controller.refresh_word_highlights()  # vocabulary changed: no re-raster needed
    argb = QColor.NameFormat.HexArgb
    seen_colours = {color.name(argb) for _rect, color in items}
    new_colours = {color.name(argb) for _rect, color in window._labels["words"]}
    assert len(seen_colours) == 2 and len(new_colours) == 1


# ------------------------------------------------------------------ EPUB


def _load_epub(controller, path, page=0, location=None):
    with patch("immersion_app.gui.controllers.pdf_controller.QTimer.singleShot"), patch(
        "immersion_app.gui.controllers.pdf_controller.save_user_data"
    ):
        controller.load_pdf(str(path), initial_page_index=page, initial_location=location)


def test_load_epub_records_epub_type_and_chapter_location(controller_factory, make_epub):
    controller, window = controller_factory()
    _load_epub(controller, make_epub(), page=2)

    entry = window.user_data["recent_files"][0]
    assert entry["type"] == "epub"
    assert entry["page_index"] == 2
    assert "chapter" in entry and "chapter_page" in entry
    assert controller.pdf_service.doc_kind == "epub"


def test_epub_navigation_and_snapshot_track_position(controller_factory, make_epub):
    controller, window = controller_factory()
    _load_epub(controller, make_epub(), page=0)

    controller.next_page()
    controller.next_page()

    assert controller.current_page_index == 2
    snapshot = controller.position_snapshot()
    assert snapshot["page_index"] == 2
    assert controller.pdf_service.page_for_location(snapshot["chapter"], snapshot["chapter_page"]) == 2


def test_epub_location_wins_over_stale_page_index(controller_factory, make_epub):
    path = make_epub()
    controller, _window = controller_factory()
    _load_epub(controller, path, page=3)
    location = controller.pdf_service.location_for_page(3)

    other, _w = controller_factory()
    _load_epub(other, path, page=0, location=location)

    assert other.current_page_index == 3


def test_epub_unresolvable_location_falls_back_to_page_index(controller_factory, make_epub):
    controller, _window = controller_factory()
    _load_epub(controller, make_epub(), page=1, location=(99, 99))

    assert controller.current_page_index == 1


def test_pdf_snapshot_has_only_page_index(controller_factory, sample_pdf):
    controller, _window = controller_factory()
    _load(controller, sample_pdf, page=2)

    assert controller.position_snapshot() == {"page_index": 2}
    assert _window.user_data["recent_files"][0]["type"] == "pdf"


def test_epub_page_renders_with_words(controller_factory, make_epub, qapp):
    controller, _window = controller_factory()
    _load_epub(controller, make_epub())

    controller.render_current_page()
    _settle(qapp, controller)

    assert controller.page_words
