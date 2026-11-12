"""MiningController: add-now / queue / process-queue flows (Anki work runs off the UI thread)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import QObject, Signal

from immersion_app.core.selection_state import SelectionState
from immersion_app.gui.controllers.mining_controller import MiningController


class FakeTranslationService(QObject):
    translation_ready = Signal(int, str, str, bool)
    translation_failed = Signal(int, str, str, bool)
    batch_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.requests = []
        self.cache = {}

    def cached_translation(self, text):
        return self.cache.get(text)

    def translate_async(self, text, visible=True):
        self.requests.append(text)
        return len(self.requests)

    def prefetch_async(self, texts):
        pass


class FakeAnkiService(QObject):
    card_added = Signal(object)
    card_add_failed = Signal(object, str, bool)
    queue_entries_processed = Signal(list, list)

    def __init__(self, connected=True):
        super().__init__()
        self.is_connected = connected
        self.add_calls = []
        self.queued = []
        self.process_calls = 0

    def add_card_async(self, sentence, word, translation, **extra):
        self.add_calls.append({"sentence": sentence, "word": word, "translation": translation, **extra})

    def queue_card(self, payload):
        self.queued.append(payload)

    def build_queue_payload(self, **fields):
        return dict(fields)

    def process_queue_async(self):
        self.process_calls += 1


class FakeWindow:
    def __init__(self):
        self.pdf_service = type("_Pdf", (), {"doc_kind": "epub"})()
        self.current_source_name = "clip.mp4"
        self.current_source_location = "00:01"
        self.mode_manager = type("_Mode", (), {"mode_string": lambda self: "video"})()
        self.queue_dialog = None
        self.status = []
        self.feedback = []
        self.recorded = []
        self.queue_refreshes = 0
        self.popover_closed = 0

    def _update_selection_panel(self):
        pass

    def _update_action_buttons(self):
        pass

    def _build_note_sentence(self):
        return "hola mundo"

    def _set_status(self, message, timeout_ms=4000):
        self.status.append(message)

    def _show_card_feedback(self, title, sentence, variant, note_id=None, reason=""):
        self.feedback.append({"title": title, "sentence": sentence, "variant": variant, "note_id": note_id, "reason": reason})

    def _record_successful_card_add(self, word):
        self.recorded.append(word)

    def _refresh_queue_summary(self):
        self.queue_refreshes += 1

    def _close_popover(self):
        self.popover_closed += 1


@pytest.fixture
def setup(qapp):
    def _make(connected=True):
        window = FakeWindow()
        selection = SelectionState()
        anki = FakeAnkiService(connected=connected)
        controller = MiningController(window, selection, FakeTranslationService(), anki, anki_analytics=None)
        selection.word = "hola"
        selection.sentence = "hola mundo"
        selection.translation = "hello"
        return controller, window, selection, anki

    return _make


def test_add_now_runs_in_background_and_reports_success(setup):
    controller, window, _selection, anki = setup()

    controller.add_now()
    assert len(anki.add_calls) == 1
    call = anki.add_calls[0]
    assert (call["sentence"], call["word"], call["translation"]) == ("hola mundo", "hola", "hello")
    assert window.recorded == []  # nothing recorded until the worker reports back

    anki.card_added.emit({"sentence": "hola mundo", "word": "hola", "translation": "hello", "note_id": 1234})
    assert window.recorded == ["hola"]
    assert window.feedback[-1]["title"] == "Added to Anki"
    assert window.feedback[-1]["note_id"] == 1234
    assert window.popover_closed == 1


def test_add_now_ignores_double_submit_while_in_flight(setup):
    controller, _window, _selection, anki = setup()
    controller.add_now()
    controller.add_now()
    assert len(anki.add_calls) == 1


def test_add_now_queues_when_anki_disconnected(setup):
    controller, window, _selection, anki = setup(connected=False)

    controller.add_now()

    assert anki.add_calls == []
    assert len(anki.queued) == 1
    assert anki.queued[0]["word"] == "hola"
    assert window.feedback[-1]["title"] == "Queued for later"
    assert window.feedback[-1]["reason"] == "AnkiConnect is not available"


def test_add_now_queues_when_connection_drops_during_add(setup):
    controller, window, _selection, anki = setup()
    controller.add_now()
    payload = anki.add_calls[0]

    anki.card_add_failed.emit(payload, "Failed to connect to AnkiConnect", True)

    assert len(anki.queued) == 1
    assert anki.queued[0]["translation"] == "hello"
    assert window.feedback[-1]["reason"] == "Failed to connect to AnkiConnect"
    assert window.recorded == []


def test_add_now_shows_non_connection_errors(setup):
    controller, window, _selection, anki = setup()
    controller.add_now()
    with patch("immersion_app.gui.controllers.mining_controller.QMessageBox.critical") as critical:
        anki.card_add_failed.emit(anki.add_calls[0], "cannot create note because it is a duplicate", False)
    critical.assert_called_once()
    assert anki.queued == []
    assert window.recorded == []
    # A new add is allowed after a failure.
    controller.add_now()
    assert len(anki.add_calls) == 2


def test_queue_payload_source_type_follows_document_kind(setup):
    controller, window, _selection, _anki = setup()
    assert controller.queue_payload()["source_type"] == "video"

    window.mode_manager = type("_Mode", (), {"mode_string": lambda self: "pdf"})()
    assert controller.queue_payload()["source_type"] == "epub"

    window.pdf_service.doc_kind = "pdf"
    assert controller.queue_payload()["source_type"] == "pdf"


def test_add_to_queue_shows_feedback(setup):
    controller, window, _selection, anki = setup()
    controller.add_to_queue()
    assert len(anki.queued) == 1
    assert window.queue_refreshes == 1
    assert window.feedback[-1]["title"] == "Saved to queue"


def test_process_queue_runs_async_and_records_successes(setup):
    controller, window, _selection, anki = setup()
    entries = [{"word": "hola"}, {"word": "adios"}]
    with patch("immersion_app.gui.controllers.mining_controller.load_queue_entries", return_value=entries):
        controller.process_queue()
        controller.process_queue()  # ignored while running
        assert anki.process_calls == 1
        with patch("immersion_app.gui.controllers.mining_controller.QMessageBox.information") as info:
            anki.queue_entries_processed.emit(entries, [])
    assert window.recorded == ["hola", "adios"]
    info.assert_called_once()


def test_manual_word_requests_translation(setup):
    controller, _window, selection, _anki = setup()
    controller.submit_manual_word("  por si acaso ")
    assert selection.word == "por si acaso"
    assert controller.translation_service.requests == ["por si acaso"]


def test_manual_word_empty_clears_selection(setup):
    controller, _window, selection, _anki = setup()
    controller.submit_manual_word("   ")
    assert selection.word == ""
    assert selection.translation == ""
