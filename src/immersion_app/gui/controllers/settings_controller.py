"""Orchestrates the Settings dialog: loads Anki options in the background and applies changes."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from immersion_app.core.anki import (
    AnkiSettings,
    check_anki_setup,
    configure_anki,
    create_deck,
    get_anki_settings,
    load_anki_options,
)
from immersion_app.core.language_config import get_language_label, list_language_codes
from immersion_app.core.paths import DATA_ROOT
from immersion_app.core.signals import safe_emit
from immersion_app.core.user_data import save_user_data
from immersion_app.gui.widgets.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)


class _AnkiOptionsSignals(QObject):
    finished = Signal(list, dict, object)  # (decks, fields_by_note_type, setup_status)
    failed = Signal(str)


class AnkiOptionsTask(QRunnable):
    """Fetch decks/note types/fields and check the candidate settings."""

    def __init__(self, settings: AnkiSettings, create_deck_name: str = ""):
        super().__init__()
        self.settings = settings
        self.create_deck_name = create_deck_name
        self.signals = _AnkiOptionsSignals()

    def run(self):
        try:
            if self.create_deck_name:
                create_deck(self.create_deck_name, self.settings.connect_url)
            decks, fields_by_note_type = load_anki_options(self.settings.connect_url)
            status = check_anki_setup(self.settings)
        except Exception as exc:
            safe_emit(self.signals.failed, str(exc))
            return
        safe_emit(self.signals.finished, decks, fields_by_note_type, status)


class SettingsController(QObject):
    """Shows the Settings dialog and applies saved values to the app.

    ``window`` provides the existing setters for languages, translation mode,
    prefetch and appearance so their side effects stay in one place.
    """

    settings_applied = Signal()

    def __init__(self, window, user_data: dict, anki_service, thread_pool: QThreadPool | None = None, parent=None):
        super().__init__(parent)
        self.window = window
        self.user_data = user_data
        self.anki_service = anki_service
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._dialog: SettingsDialog | None = None

    # ---- dialog lifecycle --------------------------------------------
    def show_dialog(self) -> None:
        languages = [(code, get_language_label(code)) for code in list_language_codes()]
        dialog = SettingsDialog(self.window, languages=languages, data_folder=str(DATA_ROOT))
        dialog.set_values(self.current_values())
        dialog.refresh_anki_requested.connect(lambda url: self._load_options(dialog, url))
        dialog.create_deck_requested.connect(lambda url, name: self._load_options(dialog, url, create_deck_name=name))
        dialog.open_data_folder_requested.connect(self.window._open_data_folder)
        dialog.start_anki_requested.connect(self.window._start_anki)
        dialog.accepted.connect(lambda: self.apply(dialog.values()))
        dialog.finished.connect(lambda _result: self._forget(dialog))
        self._dialog = dialog
        self._load_options(dialog, dialog.connect_url())
        dialog.open()

    def _forget(self, dialog: SettingsDialog) -> None:
        if self._dialog is dialog:
            self._dialog = None
        dialog.deleteLater()

    def current_values(self) -> dict:
        prefs = self.user_data.get("preferences", {})
        return {
            "anki": get_anki_settings().to_dict(),
            "learning_language": prefs.get("learning_language"),
            "native_language": prefs.get("native_language"),
            "translation_mode": prefs.get("translation_mode", "online"),
            "prefetch_enabled": prefs.get("prefetch_enabled", True),
            "theme_mode": prefs.get("theme_mode", "light"),
        }

    # ---- Anki options --------------------------------------------------
    def _load_options(self, dialog: SettingsDialog, connect_url: str, create_deck_name: str = "") -> None:
        candidate = AnkiSettings.from_dict({**dialog.values()["anki"], "connect_url": connect_url})
        dialog.set_anki_busy(True)
        dialog.set_anki_status("Creating deck…" if create_deck_name else "Contacting Anki…", "muted")
        task = AnkiOptionsTask(candidate, create_deck_name=create_deck_name)
        task.signals.finished.connect(lambda decks, fields, status: self._on_options_loaded(dialog, decks, fields, status))
        task.signals.failed.connect(lambda message: self._on_options_failed(dialog, message))
        self._thread_pool.start(task)

    def _on_options_loaded(self, dialog, decks, fields_by_note_type, status) -> None:
        if self._dialog is not dialog:
            return
        dialog.set_anki_busy(False)
        if not status.connected:
            dialog.set_anki_status(
                "Can't reach Anki. Open Anki and make sure the AnkiConnect add-on (2055492159) is installed.",
                "error",
            )
            return
        dialog.set_anki_options(decks, fields_by_note_type)
        if status.ok:
            dialog.set_anki_status("Connected. Deck, note type and fields look good.", "ok")
        else:
            dialog.set_anki_status(f"Connected, but {status.message}.", "warning")

    def _on_options_failed(self, dialog, message: str) -> None:
        if self._dialog is not dialog:
            return
        dialog.set_anki_busy(False)
        dialog.set_anki_status(f"Anki error: {message}", "error")

    # ---- apply ---------------------------------------------------------
    def apply(self, values: dict) -> None:
        anki_settings = AnkiSettings.from_dict(values.get("anki"))
        anki_changed = anki_settings != get_anki_settings()
        self.user_data["anki"] = anki_settings.to_dict()
        configure_anki(anki_settings)

        prefs = self.user_data.setdefault("preferences", {})
        if values.get("learning_language") and values["learning_language"] != prefs.get("learning_language"):
            self.window._set_learning_language(values["learning_language"])
        if values.get("native_language") and values["native_language"] != prefs.get("native_language"):
            self.window._set_native_language(values["native_language"])
        if values.get("translation_mode") in ("online", "offline") and values["translation_mode"] != self.window.translation_mode:
            self.window._toggle_translation_mode()
        if bool(values.get("prefetch_enabled", True)) != bool(prefs.get("prefetch_enabled", True)):
            self.window._on_prefetch_toggled(bool(values.get("prefetch_enabled", True)))
        if values.get("theme_mode") in ("light", "dark"):
            self.window._set_appearance_mode(values["theme_mode"])

        save_user_data(self.user_data)
        if anki_changed:
            logger.info("Anki settings changed; re-checking connection and vocabulary")
            self.anki_service.refresh_connection()
        self.settings_applied.emit()
