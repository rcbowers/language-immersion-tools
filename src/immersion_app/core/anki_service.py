"""Core service for async Anki connection state and vocabulary refresh."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from immersion_app.core.anki import fetch_deck_words, test_anki_connection

logger = logging.getLogger(__name__)


class AnkiStatusTaskSignals(QObject):
    """Signals emitted by the background Anki status task."""

    finished = Signal(int, bool, object)
    failed = Signal(int, str)


class AnkiStatusTask(QRunnable):
    """Background task that checks Anki connectivity and fetches vocabulary."""

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


class AnkiService(QObject):
    """Owns Anki connection state and async refresh flow."""

    status_check_started = Signal(int)
    connection_changed = Signal(bool)
    vocabulary_loaded = Signal(object)

    def __init__(self, thread_pool: QThreadPool | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._request_id = 0
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        """Return the most recent known connection state."""
        return self._is_connected

    def refresh_connection(self) -> None:
        """Check Anki availability in the background."""
        self._request_id += 1
        request_id = self._request_id
        logger.info("Checking Anki connection status (request_id=%s)", request_id)
        self.status_check_started.emit(request_id)
        task = AnkiStatusTask(request_id)
        task.signals.finished.connect(self._on_status_finished)
        task.signals.failed.connect(self._on_status_failed)
        self._thread_pool.start(task)

    def _on_status_finished(self, request_id: int, connected: bool, words: object) -> None:
        if request_id != self._request_id:
            logger.debug(
                "Anki status check stale (request_id=%s, current=%s), ignoring",
                request_id,
                self._request_id,
            )
            return
        vocab_count = len(words) if words is not None else 0
        logger.info(
            "Anki status checked (request_id=%s): connected=%s, vocabulary_count=%s",
            request_id,
            connected,
            vocab_count,
        )
        self._is_connected = connected
        self.connection_changed.emit(connected)
        if words is not None:
            self.vocabulary_loaded.emit(words)

    def _on_status_failed(self, request_id: int, error_message: str) -> None:
        if request_id != self._request_id:
            logger.debug(
                "Anki status failure stale (request_id=%s, current=%s), ignoring",
                request_id,
                self._request_id,
            )
            return
        logger.warning("Anki status refresh failed (request_id=%s): %s", request_id, error_message)
        self._is_connected = False
        self.connection_changed.emit(False)
