"""PDFController navigation, loading and rendering against a real PDFService and a generated PDF."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import fitz
import pytest

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
        pdf_label=SimpleNamespace(setPixmap=lambda pixmap: labels.__setitem__("pixmap", pixmap), resize=lambda size: None),
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


def test_render_extracts_words_and_prefetches(controller_factory, sample_pdf):
    controller, window = controller_factory()
    _load(controller, sample_pdf)

    controller.render_current_page()

    assert window._labels["pixmap"] is not None
    assert any(word[4].startswith("hola") for word in controller.page_word_order)
    assert "hola" in controller.mining_controller.prefetched[-1]


def test_render_inverts_page_in_dark_mode(controller_factory, sample_pdf):
    light, _ = controller_factory(dark=False)
    dark, dark_window = controller_factory(dark=True)
    for controller in (light, dark):
        _load(controller, sample_pdf)
        controller.render_current_page()
    light_pixel = light.window._labels["pixmap"].toImage().pixelColor(5, 5)
    dark_pixel = dark_window._labels["pixmap"].toImage().pixelColor(5, 5)
    assert light_pixel.lightness() > 200  # white paper
    assert dark_pixel.lightness() < 60  # inverted
