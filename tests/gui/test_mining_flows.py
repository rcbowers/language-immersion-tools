"""End-to-end mining flows through the *real* controller and services.

Only the edges are faked: the thread pools (tasks run on demand), the translation
backend, AnkiConnect (``add_anki_card``) and queue persistence. This is the README
promise: click a word -> translation appears -> Ctrl+Space adds a card (Anki up)
or queues it (Anki down), and no card is silently lost.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from immersion_app.core import anki_service as anki_service_module
from immersion_app.core.anki_service import AnkiService
from immersion_app.core.selection_state import SelectionState
from immersion_app.core.translation_service import TranslationService
from immersion_app.gui.controllers import mining_controller as mc
from immersion_app.gui.controllers.mining_controller import MiningController


class _Pool:
    def __init__(self):
        self.tasks = []

    def start(self, task):
        self.tasks.append(task)

    def run_all(self):
        tasks, self.tasks = self.tasks, []
        for task in tasks:
            task.run()

    def clear(self):
        self.tasks.clear()

    def waitForDone(self, ms):
        pass


class _Backend:
    def __init__(self):
        self.fail = None

    def translate(self, text, src, dest):
        if self.fail:
            raise RuntimeError(self.fail)
        return {"hola": "hello", "adios": "goodbye"}.get(text, f"<{text}>")


class _Window:
    def __init__(self):
        self.current_source_name = "libro.pdf"
        self.current_source_location = "Page 3"
        self.mode_manager = SimpleNamespace(mode_string=lambda: "pdf")
        self.queue_dialog = None
        self.status, self.feedback, self.recorded = [], [], []
        self.queue_refreshes = 0

    def _update_selection_panel(self):
        pass

    def _update_action_buttons(self):
        pass

    def _build_note_sentence(self):
        return "Ella dijo hola a todos."

    def _set_status(self, message, timeout_ms=4000):
        self.status.append(message)

    def _show_card_feedback(self, title, sentence, variant, note_id=None, reason=""):
        self.feedback.append({"title": title, "variant": variant, "note_id": note_id, "reason": reason})

    def _record_successful_card_add(self, word):
        self.recorded.append(word)

    def _refresh_queue_summary(self):
        self.queue_refreshes += 1

    def _close_popover(self):
        pass


@pytest.fixture
def flow(qapp, monkeypatch):
    main_pool, prefetch_pool = _Pool(), _Pool()
    backend = _Backend()
    translation = TranslationService("es", "en", mode="online", thread_pool=main_pool)
    translation._prefetch_pool = prefetch_pool
    translation._online_backend = backend

    anki_pool = _Pool()
    anki = AnkiService(thread_pool=anki_pool)
    anki._is_connected = True

    state = {"queue": [], "anki_cards": [], "anki_error": None, "log": []}

    def add_card(sentence, word, translation_text):
        if state["anki_error"] is not None:
            raise state["anki_error"]
        state["anki_cards"].append((sentence, word, translation_text))
        return 1000 + len(state["anki_cards"])

    monkeypatch.setattr(anki_service_module, "add_anki_card", add_card)
    monkeypatch.setattr(anki_service_module, "append_queue_entry", lambda e: state["queue"].append(e))
    monkeypatch.setattr(anki_service_module, "load_queue_entries", lambda: list(state["queue"]))
    monkeypatch.setattr(anki_service_module, "save_queue_entries", lambda entries: state.__setitem__("queue", list(entries)))
    monkeypatch.setattr(anki_service_module, "append_processed_log", lambda entries: state["log"].extend(entries))
    monkeypatch.setattr(mc, "load_queue_entries", lambda: list(state["queue"]))
    dialogs = []
    for name in ("critical", "information", "warning"):
        monkeypatch.setattr(mc.QMessageBox, name, lambda *a, _n=name: dialogs.append((_n, a[1:])))

    window = _Window()
    selection = SelectionState()
    controller = MiningController(window, selection, translation, anki, anki_analytics=None)
    return SimpleNamespace(
        controller=controller, window=window, selection=selection, translation=translation, anki=anki,
        main_pool=main_pool, prefetch_pool=prefetch_pool, anki_pool=anki_pool, backend=backend,
        state=state, dialogs=dialogs,
    )


def _select(flow, word):
    flow.controller.submit_manual_word(word)
    flow.main_pool.run_all()


def test_click_word_shows_translation_and_adds_card_to_anki(flow):
    _select(flow, "hola")
    assert flow.selection.word == "hola" and flow.selection.translation == "hello"

    flow.controller.add_now()
    assert flow.state["anki_cards"] == []  # runs off the UI thread
    flow.anki_pool.run_all()

    assert flow.state["anki_cards"] == [("Ella dijo hola a todos.", "hola", "hello")]
    assert flow.window.recorded == ["hola"]
    assert flow.window.feedback[-1]["title"] == "Added to Anki" and flow.window.feedback[-1]["note_id"] == 1001
    assert flow.state["queue"] == []


def test_anki_down_queues_the_card_instead_of_losing_it(flow):
    flow.anki._is_connected = False
    _select(flow, "hola")
    flow.controller.add_now()
    flow.anki_pool.run_all()

    assert flow.state["anki_cards"] == []
    assert len(flow.state["queue"]) == 1
    queued = flow.state["queue"][0]
    assert (queued["word"], queued["translation"], queued["source_name"], queued["source_type"], queued["location"]) == (
        "hola", "hello", "libro.pdf", "pdf", "Page 3",
    )
    assert flow.window.feedback[-1]["variant"] == "queued"
    assert flow.window.queue_refreshes == 1


def test_connection_lost_mid_add_queues_the_card(flow):
    _select(flow, "hola")
    flow.state["anki_error"] = ConnectionError("Anki closed")
    flow.controller.add_now()
    flow.anki_pool.run_all()

    assert flow.anki.is_connected is False
    assert [e["word"] for e in flow.state["queue"]] == ["hola"]
    assert flow.window.feedback[-1]["title"] == "Queued for later"
    assert flow.dialogs == []  # a dropped connection is not an error popup


def test_duplicate_note_error_reaches_the_user_and_is_not_queued(flow):
    _select(flow, "hola")
    flow.state["anki_error"] = RuntimeError("AnkiConnect error: cannot create note because it is a duplicate")
    flow.controller.add_now()
    flow.anki_pool.run_all()

    assert flow.state["queue"] == []
    assert flow.dialogs and flow.dialogs[0][0] == "critical" and "duplicate" in flow.dialogs[0][1][1]
    assert flow.anki.is_connected is True
    flow.controller.add_now()  # the in-flight flag was released, user can retry
    assert len(flow.anki_pool.tasks) == 1


def test_quick_second_click_discards_the_late_first_translation(flow):
    flow.controller.submit_manual_word("hola")  # request 1 in flight
    flow.controller.submit_manual_word("adios")  # user moved on
    flow.main_pool.run_all()
    assert flow.selection.word == "adios" and flow.selection.translation == "goodbye"


def test_translation_failure_is_reported_and_card_cannot_be_added(flow):
    flow.backend.fail = "HTTP 429"
    _select(flow, "hola")
    assert any("Translation failed: HTTP 429" in s for s in flow.window.status)
    assert flow.selection.translation != "hello"
    flow.controller.add_now()
    assert flow.anki_pool.tasks == [] and flow.state["queue"] == []


def test_cached_word_translates_instantly_second_time(flow):
    _select(flow, "hola")
    flow.controller.clear_selection()
    flow.controller.submit_manual_word("hola")
    assert flow.selection.translation == "hello"
    assert flow.main_pool.tasks == []  # served from cache, no new request


def test_queue_then_process_when_anki_returns(flow):
    flow.anki._is_connected = False
    for word in ("hola", "adios"):
        _select(flow, word)
        flow.controller.add_now()
    assert [e["word"] for e in flow.state["queue"]] == ["hola", "adios"]

    flow.anki._is_connected = True
    flow.state["anki_error"] = None
    flow.controller.process_queue()
    flow.anki_pool.run_all()

    assert [c[1] for c in flow.state["anki_cards"]] == ["hola", "adios"]
    assert flow.state["queue"] == []
    assert [e["word"] for e in flow.state["log"]] == ["hola", "adios"]
    assert flow.window.recorded == ["hola", "adios"]
    assert flow.dialogs[-1][0] == "information" and "Added: 2" in flow.dialogs[-1][1][1]


def test_partial_queue_failure_keeps_only_failed_entries(flow):
    flow.anki._is_connected = False
    for word in ("hola", "adios"):
        _select(flow, word)
        flow.controller.add_now()
    flow.anki._is_connected = True

    original = anki_service_module.add_anki_card

    def flaky(sentence, word, translation):
        if word == "adios":
            raise RuntimeError("AnkiConnect error: duplicate")
        return original(sentence, word, translation)

    anki_service_module.add_anki_card = flaky
    try:
        flow.controller.process_queue()
        flow.anki_pool.run_all()
    finally:
        anki_service_module.add_anki_card = original

    assert [e["word"] for e in flow.state["queue"]] == ["adios"]
    assert "Failed: 1" in flow.dialogs[-1][1][1]


def test_process_queue_with_anki_down_does_not_touch_the_queue(flow):
    flow.anki._is_connected = False
    _select(flow, "hola")
    flow.controller.add_to_queue()
    flow.controller.process_queue()
    assert [e["word"] for e in flow.state["queue"]] == ["hola"]
    assert flow.dialogs[-1][0] == "warning" and flow.anki_pool.tasks == []
