"""Core service for async Anki connection state and queue operations."""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from immersion_app.core.anki import add_anki_card, fetch_deck_words, test_anki_connection
from immersion_app.core.paths import PROCESSED_LOG_PATH
from immersion_app.core.queue_store import append_processed_log, append_queue_entry, load_queue_entries, save_queue_entries

logger = logging.getLogger(__name__)


class AnkiStatusTaskSignals(QObject):
    finished = Signal(int, bool, object)
    failed = Signal(int, str)


class AnkiStatusTask(QRunnable):
    def __init__(self, request_id: int):
        super().__init__()
        self.request_id = request_id
        self.signals = AnkiStatusTaskSignals()

    def run(self):
        try:
            connected = test_anki_connection()
            words = fetch_deck_words() if connected else None
            self.signals.finished.emit(self.request_id, connected, words)
        except RuntimeError:
            return
        except Exception as exc:
            logger.error("Anki status task failed (request_id=%s): %s", self.request_id, exc, exc_info=True)
            try:
                self.signals.failed.emit(self.request_id, str(exc))
            except RuntimeError:
                return


class AnkiAddTaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class AnkiAddTask(QRunnable):
    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        self.signals = AnkiAddTaskSignals()

    def run(self):
        try:
            note_id = add_anki_card(self.payload["sentence"], self.payload["word"], self.payload["translation"])
            result = dict(self.payload)
            result["note_id"] = note_id
            self.signals.finished.emit(result)
        except RuntimeError:
            return
        except Exception as exc:
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                return


class QueueProcessTaskSignals(QObject):
    finished = Signal(list, list)
    failed = Signal(str)


class QueueProcessTask(QRunnable):
    def __init__(self, entries: list[dict]):
        super().__init__()
        self.entries = entries
        self.signals = QueueProcessTaskSignals()

    def run(self):
        successful_entries = []
        failed_entries = []
        sentence_counts: dict[str, int] = {}
        try:
            for entry in self.entries:
                sentence = entry["sentence"]
                sentence_counts[sentence] = sentence_counts.get(sentence, 0) + 1
                sentence_for_note = sentence if sentence_counts[sentence] == 1 else f"{sentence} ({sentence_counts[sentence]})"
                try:
                    add_anki_card(sentence_for_note, entry["word"], entry["translation"])
                    successful_entries.append(entry)
                except Exception:
                    failed_entries.append(entry)
            self.signals.finished.emit(successful_entries, failed_entries)
        except RuntimeError:
            return
        except Exception as exc:
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                return


class AnkiService(QObject):
    status_check_started = Signal(int)
    connection_changed = Signal(bool)
    vocabulary_loaded = Signal(object)
    card_added = Signal(object)
    card_failed = Signal(str)
    queue_entry_added = Signal(object)
    queue_processed = Signal(int, int, str)

    def __init__(self, thread_pool: QThreadPool | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._request_id = 0
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def refresh_connection(self) -> None:
        self._request_id += 1
        request_id = self._request_id
        self.status_check_started.emit(request_id)
        task = AnkiStatusTask(request_id)
        task.signals.finished.connect(self._on_status_finished)
        task.signals.failed.connect(self._on_status_failed)
        self._thread_pool.start(task)

    def queue_card(self, payload: dict):
        append_queue_entry(payload)
        self.queue_entry_added.emit(payload)

    def build_queue_payload(self, *, word: str, sentence: str, translation: str, source_name: str, source_type: str, location: str):
        return {
            "sentence": sentence or word,
            "word": word,
            "translation": translation,
            "source_name": source_name,
            "source_type": source_type,
            "location": location,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "status": "queued",
        }

    def add_card_async(self, sentence: str, word: str, translation: str):
        payload = {"sentence": sentence, "word": word, "translation": translation}
        task = AnkiAddTask(payload)
        task.signals.finished.connect(self.card_added.emit)
        task.signals.failed.connect(self.card_failed.emit)
        self._thread_pool.start(task)

    def add_card_now(self, sentence: str, word: str, translation: str):
        note_id = add_anki_card(sentence, word, translation)
        payload = {"sentence": sentence, "word": word, "translation": translation, "note_id": note_id}
        self.card_added.emit(payload)
        return note_id

    def process_queue_async(self):
        entries = load_queue_entries()
        task = QueueProcessTask(entries)
        task.signals.finished.connect(self._on_queue_processed)
        task.signals.failed.connect(self.card_failed.emit)
        self._thread_pool.start(task)

    def process_queue_now(self):
        entries = load_queue_entries()
        successful_entries = []
        failed_entries = []
        sentence_counts: dict[str, int] = {}
        for entry in entries:
            sentence = entry["sentence"]
            sentence_counts[sentence] = sentence_counts.get(sentence, 0) + 1
            sentence_for_note = sentence if sentence_counts[sentence] == 1 else f"{sentence} ({sentence_counts[sentence]})"
            try:
                add_anki_card(sentence_for_note, entry["word"], entry["translation"])
                successful_entries.append(entry)
            except Exception:
                failed_entries.append(entry)
        self._finalize_queue_processing(successful_entries, failed_entries)
        return successful_entries, failed_entries

    def _finalize_queue_processing(self, successful_entries: list[dict], failed_entries: list[dict]):
        if successful_entries:
            append_processed_log(successful_entries)
        save_queue_entries(failed_entries)
        self.queue_processed.emit(len(successful_entries), len(failed_entries), str(PROCESSED_LOG_PATH))

    def _on_status_finished(self, request_id: int, connected: bool, words: object) -> None:
        if request_id != self._request_id:
            return
        self._is_connected = connected
        self.connection_changed.emit(connected)
        if words is not None:
            self.vocabulary_loaded.emit(words)

    def _on_status_failed(self, request_id: int, error_message: str) -> None:
        if request_id != self._request_id:
            return
        logger.warning("Anki status refresh failed (request_id=%s): %s", request_id, error_message)
        self._is_connected = False
        self.connection_changed.emit(False)

    def _on_queue_processed(self, successful_entries: list[dict], failed_entries: list[dict]):
        self._finalize_queue_processing(successful_entries, failed_entries)
