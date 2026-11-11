"""Settings dialog (presentation) and SettingsController (apply logic)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from immersion_app.core import anki
from immersion_app.core.anki import AnkiSettings
from immersion_app.core.user_data import default_user_data
from immersion_app.gui.controllers.settings_controller import SettingsController
from immersion_app.gui.widgets.settings_dialog import SettingsDialog

LANGUAGES = [("es", "Spanish"), ("fr", "French"), ("en", "English")]


@pytest.fixture(autouse=True)
def restore_anki_settings():
    previous = anki.get_anki_settings()
    yield
    anki.configure_anki(previous)


def _values(**overrides):
    values = {
        "anki": AnkiSettings(deck_name="Spanish::Mining").to_dict(),
        "learning_language": "es",
        "native_language": "en",
        "translation_mode": "online",
        "prefetch_enabled": True,
        "theme_mode": "light",
    }
    values.update(overrides)
    return values


def test_dialog_round_trips_values(qtbot):
    dialog = SettingsDialog(languages=LANGUAGES, data_folder="/tmp/data")
    qtbot.addWidget(dialog)
    dialog.set_values(_values(learning_language="fr", theme_mode="dark", prefetch_enabled=False))

    result = dialog.values()
    assert result["anki"]["deck_name"] == "Spanish::Mining"
    assert result["anki"]["tags"] == list(anki.DEFAULT_TAGS)
    assert result["learning_language"] == "fr"
    assert result["theme_mode"] == "dark"
    assert result["prefetch_enabled"] is False


def test_dialog_options_keep_current_choice_and_fill_fields(qtbot):
    dialog = SettingsDialog(languages=LANGUAGES, data_folder="/tmp/data")
    qtbot.addWidget(dialog)
    dialog.set_values(_values())

    dialog.set_anki_options(
        ["Default", "Spanish::Mining"],
        {"Basic": ["Front", "Back"], "Sentence": ["Expression", "Meaning", "Notes"]},
    )
    assert dialog.deck_combo.currentText() == "Spanish::Mining"
    assert dialog.note_type_combo.currentText() == "Basic"

    dialog.note_type_combo.setCurrentText("Sentence")
    assert dialog.sentence_field_combo.currentText() == "Expression"
    assert dialog.translation_field_combo.currentText() == "Meaning"


def test_dialog_emits_refresh_and_create_deck(qtbot):
    dialog = SettingsDialog(languages=LANGUAGES, data_folder="/tmp/data")
    qtbot.addWidget(dialog)
    dialog.set_values(_values())
    dialog.deck_combo.setEditText("New Deck")

    with qtbot.waitSignal(dialog.create_deck_requested) as blocker:
        dialog.create_deck_button.click()
    assert blocker.args == ["http://localhost:8765", "New Deck"]

    with qtbot.waitSignal(dialog.refresh_anki_requested) as blocker:
        dialog.refresh_button.click()
    assert blocker.args == ["http://localhost:8765"]


class _Window:
    def __init__(self, user_data):
        self.user_data = user_data
        self.translation_mode = "online"
        self.calls = []

    def _set_learning_language(self, code):
        self.calls.append(("learning", code))
        self.user_data["preferences"]["learning_language"] = code

    def _set_native_language(self, code):
        self.calls.append(("native", code))

    def _toggle_translation_mode(self):
        self.calls.append(("toggle",))

    def _on_prefetch_toggled(self, enabled):
        self.calls.append(("prefetch", enabled))

    def _set_appearance_mode(self, mode):
        self.calls.append(("theme", mode))

    def _open_data_folder(self):
        pass

    def _start_anki(self):
        pass


class _AnkiService:
    def __init__(self):
        self.refreshes = 0

    def refresh_connection(self):
        self.refreshes += 1


def test_apply_saves_anki_settings_and_refreshes_connection(qapp):
    user_data = default_user_data()
    window = _Window(user_data)
    service = _AnkiService()
    controller = SettingsController(window, user_data, service)

    with patch("immersion_app.gui.controllers.settings_controller.save_user_data") as save:
        controller.apply(_values(learning_language="fr", translation_mode="offline", prefetch_enabled=False))

    assert anki.get_anki_settings().deck_name == "Spanish::Mining"
    assert user_data["anki"]["deck_name"] == "Spanish::Mining"
    assert ("learning", "fr") in window.calls
    assert ("toggle",) in window.calls
    assert ("prefetch", False) in window.calls
    assert service.refreshes == 1
    save.assert_called_once_with(user_data)


def test_apply_without_anki_change_does_not_recheck(qapp):
    user_data = default_user_data()
    anki.configure_anki(AnkiSettings(deck_name="Spanish::Mining"))
    service = _AnkiService()
    controller = SettingsController(_Window(user_data), user_data, service)

    with patch("immersion_app.gui.controllers.settings_controller.save_user_data"):
        controller.apply(_values())

    assert service.refreshes == 0


def test_anki_settings_from_dict_normalises_bad_input():
    settings = AnkiSettings.from_dict({"deck_name": "  ", "tags": "a, b  c", "connect_url": None})
    assert settings.deck_name == anki.DEFAULT_DECK_NAME
    assert settings.connect_url == anki.DEFAULT_ANKI_CONNECT_URL
    assert settings.tags == ("a", "b", "c")
    assert AnkiSettings.from_dict(settings.to_dict()) == settings
