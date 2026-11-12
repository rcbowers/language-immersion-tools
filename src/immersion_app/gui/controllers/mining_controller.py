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
        self._add_in_flight = False
        self._queue_processing = False

        self.selection.selection_changed.connect(self.window._update_selection_panel)
        self.selection.selection_changed.connect(self.window._update_action_buttons)
        self.translation_service.translation_ready.connect(self._on_translation_ready)
        self.translation_service.translation_failed.connect(self._on_translation_failed)
        self.translation_service.batch_failed.connect(lambda message: logger.warning("Batch translation prefetch failed: %s", message))
        self.anki_service.card_added.connect(self._on_card_added)
        self.anki_service.card_add_failed.connect(self._on_card_add_failed)
        self.anki_service.queue_entries_processed.connect(self._on_queue_entries_processed)

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
            source_type=self._source_type(),
            location=self.window.current_source_location,
        )

    def _has_usable_translation(self) -> bool:
        """True when the selection has a real translation (not empty, pending or an error message)."""
        translation = self.selection.translation
        return bool(
            self.selection.word
            and translation
            and translation != "translating..."
            and not translation.startswith("Translation error:")
        )

    def add_now(self):
        """Add the current selection to Anki on a worker thread (never blocks the UI)."""
        if not self._has_usable_translation():
            return
        if self._add_in_flight:
            return
        if not self.anki_service.is_connected:
            self.queue_for_later("AnkiConnect is not available")
            return
        note_sentence = self.window._build_note_sentence()
        # Capture everything needed now: the selection may change before the worker finishes.
        queue_payload = self.queue_payload()
        self._add_in_flight = True
        self.window._set_status("Adding to Anki…")
        self.anki_service.add_card_async(
            note_sentence,
            self.selection.word,
            self.selection.translation,
            queue_payload=queue_payload,
        )

    def _on_card_added(self, result: dict):
        self._add_in_flight = False
        self.window._record_successful_card_add(result["word"])
        self.window._show_card_feedback("Added to Anki", result["sentence"], "added", note_id=result.get("note_id"))
        self.window._close_popover()

    def _on_card_add_failed(self, payload: dict, message: str, is_connection_error: bool):
        self._add_in_flight = False
        if is_connection_error:
            queue_payload = payload.get("queue_payload")
            if queue_payload:
                self._queue_payload_for_later(queue_payload, message)
            return
        QMessageBox.critical(self.window, "Anki Add Failed", message)

    def add_to_queue(self):
        if not self._has_usable_translation():
            return
        try:
            payload = self.queue_payload()
            self.anki_service.queue_card(payload)
            self.window._refresh_queue_summary()
            self.window._show_card_feedback("Saved to queue", payload["sentence"], "queued")
        except Exception as exc:
            QMessageBox.critical(self.window, "Queue Write Failed", str(exc))

    def queue_for_later(self, reason: str):
        self._queue_payload_for_later(self.queue_payload(), reason)

    def _queue_payload_for_later(self, payload: dict, reason: str):
        try:
            self.anki_service.queue_card(payload)
            self.window._refresh_queue_summary()
            self.window._show_card_feedback("Queued for later", payload["sentence"], "queued", reason=reason)
        except Exception as exc:
            QMessageBox.critical(self.window, "Queue Write Failed", str(exc))

    def process_queue(self):
        """Send all queued cards to Anki on a worker thread."""
        if self._queue_processing:
            return
        entries_count = len(load_queue_entries())
        if not entries_count:
            QMessageBox.information(self.window, "Queue Empty", "No queued cards found.")
            return
        if not self.anki_service.is_connected:
            QMessageBox.warning(self.window, "Anki Not Connected", "AnkiConnect is not available.")
            return
        self._queue_processing = True
        self.window._set_status(f"Sending {entries_count} queued card(s) to Anki…")
        self.anki_service.process_queue_async()

    def _on_queue_entries_processed(self, successful_entries: list, failed_entries: list):
        was_user_request = self._queue_processing
        self._queue_processing = False
        for entry in successful_entries:
            self.window._record_successful_card_add(entry["word"])
        self.window._refresh_queue_summary()
        if hasattr(self.window, "queue_dialog") and self.window.queue_dialog is not None:
            self.window.queue_dialog.refresh(load_queue_entries())
        if not was_user_request:
            return
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

    def _source_type(self) -> str:
        """Mode string, refined to the document kind ("pdf"/"epub") while reading a document."""
        source_type = self.window.mode_manager.mode_string()
        pdf_service = getattr(self.window, "pdf_service", None)
        if source_type == "pdf" and isinstance(getattr(pdf_service, "doc_kind", None), str):
            return pdf_service.doc_kind
        return source_type
