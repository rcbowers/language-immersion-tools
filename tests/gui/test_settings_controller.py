"""Tests for SettingsController (apply, Anki options loading) and AnalyticsController."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal

from immersion_app.core import anki
from immersion_app.core.anki import AnkiSetupStatus, AnkiSettings
from immersion_app.gui.controllers import analytics_controller as ac
from immersion_app.gui.controllers import settings_controller as sc


class _Calls(list):
    def __call__(self, *args, **kwargs):
        self.append((args, kwargs))


class _Pool:
    def __init__(self):
        self.tasks = []

    def start(self, task):
        self.tasks.append(task)

    def run_all(self):
        tasks, self.tasks = self.tasks, []
        for task in tasks:
            task.run()


class _Dialog:
    def __init__(self, anki_values=None):
        self._anki_values = anki_values or AnkiSettings().to_dict()
        self.busy = []
        self.status = []
        self.options = []

    def values(self):
        return {"anki": self._anki_values}

    def set_anki_busy(self, busy):
        self.busy.append(busy)

    def set_anki_status(self, text, level):
        self.status.append((text, level))

    def set_anki_options(self, decks, fields):
        self.options.append((decks, fields))


def _window(translation_mode="online"):
    return SimpleNamespace(
        translation_mode=translation_mode,
        _set_learning_language=_Calls(),
        _set_native_language=_Calls(),
        _toggle_translation_mode=_Calls(),
        _on_prefetch_toggled=_Calls(),
        _set_appearance_mode=_Calls(),
    )


@pytest.fixture
def env(monkeypatch):
    original = anki.get_anki_settings()
    saved = _Calls()
    monkeypatch.setattr(sc, "save_user_data", saved)
    anki.configure_anki(AnkiSettings())
    yield SimpleNamespace(saved=saved)
    anki.configure_anki(original)


def _controller(window=None, prefs=None, pool=None):
    user_data = {"preferences": prefs if prefs is not None else
                 {"learning_language": "es", "native_language": "en", "prefetch_enabled": True}}
    service = SimpleNamespace(refresh_connection=_Calls())
    controller = sc.SettingsController(window or _window(), user_data, service, thread_pool=pool or _Pool())
    return controller, user_data, service


# --- apply ---------------------------------------------------------------


def test_apply_persists_every_section_and_calls_window_setters(env):
    window = _window(translation_mode="online")
    controller, user_data, service = _controller(window)
    applied = []
    controller.settings_applied.connect(lambda: applied.append(True))
    controller.apply(
        {
            "anki": {"deck_name": "Mine", "note_type": "Basic", "sentence_field": "Front", "translation_field": "Back",
                     "connect_url": "http://localhost:8765", "tags": "a b"},
            "learning_language": "fr",
            "native_language": "it",
            "translation_mode": "offline",
            "prefetch_enabled": False,
            "theme_mode": "dark",
        }
    )
    assert user_data["anki"]["deck_name"] == "Mine" and user_data["anki"]["tags"] == ["a", "b"]
    assert anki.get_anki_settings().deck_name == "Mine"  # configure_anki called
    assert window._set_learning_language == [(("fr",), {})]
    assert window._set_native_language == [(("it",), {})]
    assert len(window._toggle_translation_mode) == 1
    assert window._on_prefetch_toggled == [((False,), {})]
    assert window._set_appearance_mode == [(("dark",), {})]
    assert len(env.saved) == 1
    assert len(service.refresh_connection) == 1  # Anki settings changed
    assert applied == [True]


def test_apply_with_no_changes_only_saves(env):
    window = _window(translation_mode="online")
    controller, user_data, service = _controller(window)
    controller.apply(
        {
            "anki": AnkiSettings().to_dict(),
            "learning_language": "es",
            "native_language": "en",
            "translation_mode": "online",
            "prefetch_enabled": True,
        }
    )
    assert window._set_learning_language == [] and window._set_native_language == []
    assert window._toggle_translation_mode == [] and window._on_prefetch_toggled == []
    assert service.refresh_connection == []  # Anki unchanged: no reconnect
    assert len(env.saved) == 1


def test_apply_ignores_invalid_modes(env):
    window = _window()
    controller, *_ = _controller(window)
    controller.apply({"anki": {}, "translation_mode": "carrier-pigeon", "theme_mode": "neon"})
    assert window._toggle_translation_mode == [] and window._set_appearance_mode == []


def test_apply_blank_anki_values_fall_back_to_defaults(env):
    controller, user_data, service = _controller()
    controller.apply({"anki": {"deck_name": "  ", "note_type": ""}})
    assert user_data["anki"]["deck_name"] == anki.DEFAULT_DECK_NAME
    assert user_data["anki"]["note_type"] == anki.DEFAULT_NOTE_TYPE


def test_current_values_reflect_preferences_and_anki(env):
    anki.configure_anki(AnkiSettings(deck_name="D"))
    controller, *_ = _controller(prefs={"learning_language": "ja", "native_language": "en"})
    values = controller.current_values()
    assert values["anki"]["deck_name"] == "D"
    assert values["learning_language"] == "ja"
    assert values["translation_mode"] == "online" and values["prefetch_enabled"] is True and values["theme_mode"] == "light"


# --- options loading -----------------------------------------------------


def test_load_options_runs_task_and_reports(env, monkeypatch):
    pool = _Pool()
    controller, *_ = _controller(pool=pool)
    dialog = _Dialog()
    controller._dialog = dialog
    status = AnkiSetupStatus(connected=True, deck_exists=True, note_type_exists=True, message="Ready")
    monkeypatch.setattr(sc, "load_anki_options", lambda url: (["D1"], {"Basic": ["Front", "Back"]}))
    monkeypatch.setattr(sc, "check_anki_setup", lambda settings: status)
    controller._load_options(dialog, "http://localhost:8765")
    assert dialog.busy == [True] and dialog.status[0] == ("Contacting Anki…", "muted")
    pool.run_all()
    assert dialog.busy == [True, False]
    assert dialog.options == [(["D1"], {"Basic": ["Front", "Back"]})]
    assert dialog.status[-1][1] == "ok"


def test_options_loaded_not_ok_shows_warning(env):
    controller, *_ = _controller()
    dialog = _Dialog()
    controller._dialog = dialog
    status = AnkiSetupStatus(connected=True, deck_exists=False, message="deck 'X' not found")
    controller._on_options_loaded(dialog, ["A"], {}, status)
    assert dialog.options and dialog.status[-1] == ("Connected, but deck 'X' not found.", "warning")


def test_options_loaded_when_unreachable_shows_error_and_no_options(env):
    controller, *_ = _controller()
    dialog = _Dialog()
    controller._dialog = dialog
    controller._on_options_loaded(dialog, [], {}, AnkiSetupStatus(connected=False, message="x"))
    assert dialog.options == []
    assert dialog.status[-1][1] == "error" and "AnkiConnect" in dialog.status[-1][0]
    assert dialog.busy == [False]


def test_options_failed_shows_error(env):
    controller, *_ = _controller()
    dialog = _Dialog()
    controller._dialog = dialog
    controller._on_options_failed(dialog, "boom")
    assert dialog.status == [("Anki error: boom", "error")] and dialog.busy == [False]


def test_results_for_a_closed_dialog_are_ignored(env):
    controller, *_ = _controller()
    old, current = _Dialog(), _Dialog()
    controller._dialog = current
    controller._on_options_loaded(old, ["A"], {}, AnkiSetupStatus(connected=True))
    controller._on_options_failed(old, "late")
    assert old.options == [] and old.status == [] and old.busy == []
    controller._dialog = None
    controller._on_options_failed(current, "late")
    assert current.status == []


def test_create_deck_status_text(env, monkeypatch):
    pool = _Pool()
    controller, *_ = _controller(pool=pool)
    dialog = _Dialog()
    controller._dialog = dialog
    controller._load_options(dialog, "http://localhost:8765", create_deck_name="New")
    assert dialog.status[0] == ("Creating deck…", "muted")


def test_options_task_creates_deck_before_listing(monkeypatch):
    order = []
    monkeypatch.setattr(sc, "create_deck", lambda name, url: order.append(("create", name, url)))
    monkeypatch.setattr(sc, "load_anki_options", lambda url: order.append(("load", url)) or ([], {}))
    status = AnkiSetupStatus(connected=True)
    monkeypatch.setattr(sc, "check_anki_setup", lambda settings: order.append("check") or status)
    task = sc.AnkiOptionsTask(AnkiSettings(connect_url="http://x"), create_deck_name="Fresh")
    done = []
    task.signals.finished.connect(lambda *a: done.append(a))
    task.run()
    assert order == [("create", "Fresh", "http://x"), ("load", "http://x"), "check"]
    assert done[0][2] is status


def test_options_task_skips_create_when_no_name(monkeypatch):
    monkeypatch.setattr(sc, "create_deck", lambda *a: pytest.fail("must not create a deck"))
    monkeypatch.setattr(sc, "load_anki_options", lambda url: ([], {}))
    monkeypatch.setattr(sc, "check_anki_setup", lambda settings: AnkiSetupStatus(connected=True))
    task = sc.AnkiOptionsTask(AnkiSettings())
    done = []
    task.signals.finished.connect(lambda *a: done.append(a))
    task.run()
    assert done


def test_options_task_failure_emits_failed(monkeypatch):
    def boom(url):
        raise ConnectionError("Anki is closed")

    monkeypatch.setattr(sc, "load_anki_options", boom)
    task = sc.AnkiOptionsTask(AnkiSettings())
    failed = []
    task.signals.failed.connect(failed.append)
    task.run()
    assert failed == ["Anki is closed"]


def test_forget_clears_only_the_current_dialog(env):
    controller, *_ = _controller()
    current, other = SimpleNamespace(deleteLater=_Calls()), SimpleNamespace(deleteLater=_Calls())
    controller._dialog = current
    controller._forget(other)
    assert controller._dialog is current and len(other.deleteLater) == 1
    controller._forget(current)
    assert controller._dialog is None


# --- analytics controller ------------------------------------------------


class _Manager(QObject):
    stats_changed = Signal()

    def __init__(self):
        super().__init__()
        self.refreshed = 0

    def get_dashboard_data(self):
        return {"words": 3}

    def refresh(self):
        self.refreshed += 1


class _FakeAnalyticsDialog:
    instances = []

    def __init__(self, parent):
        self.rendered = []
        self.themed = 0
        self.shown = 0
        type(self).instances.append(self)

    def refresh_theme(self):
        self.themed += 1

    def render_snapshot(self, data):
        self.rendered.append(data)

    def show(self):
        self.shown += 1

    def raise_(self):
        pass

    def activateWindow(self):
        pass


@pytest.fixture
def analytics(monkeypatch):
    _FakeAnalyticsDialog.instances = []
    monkeypatch.setattr(ac, "ActivityAnalyticsDialog", _FakeAnalyticsDialog)
    manager = _Manager()
    return ac.AnalyticsController(SimpleNamespace(), manager), manager


def test_stats_change_without_dialog_does_nothing(analytics):
    controller, manager = analytics
    manager.stats_changed.emit()
    assert _FakeAnalyticsDialog.instances == []


def test_show_dialog_creates_once_and_renders(analytics):
    controller, manager = analytics
    controller.show_dialog()
    controller.show_dialog()
    assert len(_FakeAnalyticsDialog.instances) == 1
    dialog = _FakeAnalyticsDialog.instances[0]
    assert dialog.rendered == [{"words": 3}, {"words": 3}] and dialog.shown == 2


def test_stats_change_refreshes_existing_dialog(analytics):
    controller, manager = analytics
    controller.show_dialog()
    manager.stats_changed.emit()
    assert len(_FakeAnalyticsDialog.instances[0].rendered) == 2


def test_refresh_delegates_to_manager(analytics):
    controller, manager = analytics
    controller.refresh()
    assert manager.refreshed == 1
