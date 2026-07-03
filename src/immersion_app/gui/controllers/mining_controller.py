from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMessageBox

from immersion_app.core.paths import PROCESSED_LOG_PATH
from immersion_app.core.queue_store import load_queue_entries

logger = logging.getLogger(__name__)


class MiningController(QObject):
    def __init__(self, window, selection_state, translation_service, anki_service, anki_analytics, parent=None):
        super().__init__(parent)
        self.window = window
        self.selection = selection_state
        self.translation_service = translation_service
        self.anki_service = anki_service
        self.anki_analytics = anki_analytics
        self.current_request_id = 0
        self._pending_translation_text = ""

        self.selection.selection_changed.connect(self.window._update_selection_panel)
        self.selection.selection_changed.connect(self.window._update_action_buttons)
        self.translation_service.translation_ready.connect(self._on_translation_ready)
        self.translation_service.translation_failed.connect(self._on_translation_failed)
        self.translation_service.batch_failed.connect(lambda message: logger.warning("Batch translation prefetch failed: %s", message))

    def set_languages(self, learning_language: str, native_language: str):
        self.translation_service.set_languages(learning_language, native_language)

    def set_translation_mode(self, mode: str):
        self.translation_service.set_mode(mode)

    def request_translation(self, text: str):
        if not text:
            return
        self._pending_translation_text = text
        cached = self.translation_service.cached_translation(text)
        if cached is not None:
            self.selection.set_translation(cached)
            return
        request_id = self.translation_service.translate_async(text, visible=True)
        if request_id is None:
            return
        if request_id != 0:
            self.current_request_id = request_id
            self.selection.set_translation_pending()

    def prefetch_translations(self, texts: list[str]):
        self.translation_service.prefetch_async(texts)

    def submit_manual_word(self, text: str):
        text = text.strip()
        if not text:
            self.selection.clear_all()
            return
        self.selection.set_manual_word(text)
        self.request_translation(text)

    def clear_selection(self):
        self.selection.clear_all()

    def queue_payload(self):
        return self.anki_service.build_queue_payload(
            word=self.selection.word,
            sentence=self.selection.sentence or self.selection.word,
            translation=self.selection.translation,
            source_name=self.window.current_source_name,
            source_type=self.window.mode_manager.mode_string(),
            location=self.window.current_source_location,
        )

    def add_now(self):
        if not self.selection.word or not self.selection.translation or self.selection.translation == "translating...":
            return
        if not self.anki_service.is_connected:
            self.queue_for_later("AnkiConnect is not available")
            return
        note_sentence = self.window._build_note_sentence()
        try:
            note_id = self.anki_service.add_card_now(note_sentence, self.selection.word, self.selection.translation)
        except ConnectionError as exc:
            self.queue_for_later(str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self.window, "Anki Add Failed", str(exc))
            return
        self.window._record_successful_card_add(self.selection.word)
        self.window._show_card_feedback("Added to Anki", note_sentence, "added", note_id=note_id)
        self.window._close_popover()

    def add_to_queue(self):
        if not self.selection.word or not self.selection.translation or self.selection.translation == "translating...":
            return
        try:
            payload = self.queue_payload()
            self.anki_service.queue_card(payload)
            self.window._refresh_queue_summary()
            self.window._show_card_feedback("Saved to queue", payload["sentence"], "queued")
        except Exception as exc:
            QMessageBox.critical(self.window, "Queue Write Failed", str(exc))

    def queue_for_later(self, reason: str):
        payload = self.queue_payload()
        try:
            self.anki_service.queue_card(payload)
            self.window._refresh_queue_summary()
            self.window._show_card_feedback("Queued for later", payload["sentence"], "queued", reason=reason)
        except Exception as exc:
            QMessageBox.critical(self.window, "Queue Write Failed", str(exc))

    def process_queue(self):
        entries_count = len(load_queue_entries())
        if not entries_count:
            QMessageBox.information(self.window, "Queue Empty", "No queued cards found.")
            return
        if not self.anki_service.is_connected:
            QMessageBox.warning(self.window, "Anki Not Connected", "AnkiConnect is not available.")
            return
        successful_entries, failed_entries = self.anki_service.process_queue_now()
        for entry in successful_entries:
            self.window._record_successful_card_add(entry["word"])
        self.window._refresh_queue_summary()
        QMessageBox.information(
            self.window,
            "Queue Processed",
            f"Added: {len(successful_entries)}\nFailed: {len(failed_entries)}\nLog: {PROCESSED_LOG_PATH}",
        )

    def _on_translation_ready(self, request_id: int, source_text: str, translated_text: str, visible: bool):
        if not visible:
            return
        if request_id and request_id != self.current_request_id:
            return
        if source_text != self._pending_translation_text:
            return
        self.selection.set_translation(translated_text)

    def _on_translation_failed(self, request_id: int, source_text: str, error_message: str, visible: bool):
        if not visible:
            return
        if request_id and request_id != self.current_request_id:
            return
        if source_text != self._pending_translation_text:
            return
        self.selection.set_translation_error(error_message)
        self.window._set_status(f"Translation failed: {error_message}")
