"""Smoke test for the real main window (offscreen Qt, no Anki, no network).

``main_window.py`` is a known problem file; one construct/show/close test covers most of
its start-up code and guards the creation-order ``hasattr`` checks. Logic extracted from
the window later should get its own tests (see AGENTS.md).
"""

from __future__ import annotations

import json

import pytest

from immersion_app.core import user_data
from immersion_app.core.anki_service import AnkiService
from immersion_app.core.mode import WorkspaceMode
from immersion_app.core.translation_service import TranslationService
from immersion_app.gui import main_window as mw


class _OfflineAnkiService(AnkiService):
    """Real signals and state, but never talks to AnkiConnect."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.refresh_calls = 0

    def refresh_connection(self) -> None:
        self.refresh_calls += 1
        self.status_check_started.emit(self.refresh_calls)


class _FakeAvailabilityTranslationService(TranslationService):
    """Availability probes answer instantly from a dict instead of touching the network."""

    probe_result = {"online": True, "offline": False}

    def check_availability_async(self) -> None:
        self._on_availability_checked(dict(type(self).probe_result))


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    state_path = tmp_path / "state" / "user.json"
    monkeypatch.setattr(user_data, "USER_STATE_PATH", state_path)
    monkeypatch.setattr(user_data, "LEGACY_USER_STATE_PATH", tmp_path / "legacy.json")
    monkeypatch.setattr(mw, "AnkiService", _OfflineAnkiService)
    monkeypatch.setattr(mw, "TranslationService", _FakeAvailabilityTranslationService)
    monkeypatch.setattr(mw, "load_snapshot", lambda: set())
    monkeypatch.setattr(mw, "save_snapshot", lambda words: None)
    _FakeAvailabilityTranslationService.probe_result = {"online": True, "offline": False}
    win = mw.UnifiedSentenceMinerWindow()
    qtbot.addWidget(win)
    win._state_path = state_path
    yield win
    win._block_detector.stop()


def _wait_for_startup(qtbot, win):
    qtbot.waitUntil(lambda: win._startup_overlay is None, timeout=5000)


def test_window_constructs_shows_and_starts_in_welcome_mode(qtbot, window):
    window.show()
    _wait_for_startup(qtbot, window)
    assert window.isVisible()
    assert window.mode_manager.current_mode == WorkspaceMode.WELCOME
    assert window.windowTitle() == "Language Immersion Tools Workspace"
    assert window.anki_service.refresh_calls == 1  # status checked once at start, not per widget


def test_all_controllers_are_wired(window):
    for name in (
        "mining_controller", "pdf_controller", "video_controller", "workspace_controller",
        "analytics_controller", "settings_controller", "command_bar", "subtitle_label", "transport_bar",
    ):
        assert getattr(window, name) is not None, name


def test_close_event_flushes_user_data(qtbot, window):
    window.show()
    _wait_for_startup(qtbot, window)
    window.user_data["analytics"]["cards_added_total"] = 7
    window.close()
    assert window._state_path.exists()
    saved = json.loads(window._state_path.read_text(encoding="utf-8"))
    assert saved["analytics"]["cards_added_total"] == 7
    assert saved["last_session"]["pdf_path"] == "" and saved["last_session"]["video_path"] == ""
    assert not window._state_path.with_suffix(".tmp").exists()


def test_translation_mode_toggle_checks_availability_then_falls_back(qtbot, window):
    _wait_for_startup(qtbot, window)
    window.translation_mode = "online"
    window.translation_service.set_mode("online")
    # Offline is reported unavailable: switching must not happen and the user is told.
    window._toggle_translation_mode()
    assert window.translation_mode == "online"
    # Offline becomes available: the re-check lets the switch go through.
    _FakeAvailabilityTranslationService.probe_result = {"online": True, "offline": True}
    window._toggle_translation_mode()
    assert window.translation_mode == "offline"
    assert window.translation_service.translation_mode == "offline"


def test_unavailable_saved_mode_falls_back_at_startup(qtbot, tmp_path, monkeypatch):
    """A saved 'offline' mode with offline unavailable must fall back to online, not stay broken."""
    state_path = tmp_path / "state" / "user.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"preferences": {"translation_mode": "offline"}}), encoding="utf-8")
    monkeypatch.setattr(user_data, "USER_STATE_PATH", state_path)
    monkeypatch.setattr(user_data, "LEGACY_USER_STATE_PATH", tmp_path / "legacy.json")
    monkeypatch.setattr(mw, "AnkiService", _OfflineAnkiService)
    monkeypatch.setattr(mw, "TranslationService", _FakeAvailabilityTranslationService)
    monkeypatch.setattr(mw, "load_snapshot", lambda: set())
    _FakeAvailabilityTranslationService.probe_result = {"online": True, "offline": False}
    win = mw.UnifiedSentenceMinerWindow()
    qtbot.addWidget(win)
    try:
        assert win.translation_mode == "online"
    finally:
        win._block_detector.stop()
