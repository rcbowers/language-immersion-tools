"""Translation state and background execution service."""

from __future__ import annotations

import logging
import socket

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from immersion_app.core.language_config import get_google_language_code, get_marian_language_code
from immersion_app.integrations.translation_backends import MarianMTTranslationBackend, OnlineTranslationBackend

logger = logging.getLogger(__name__)


class TranslateSignals(QObject):
    finished = Signal(int, str, str, bool)
    failed = Signal(int, str, str, bool)


class TranslateTask(QRunnable):
    def __init__(self, request_id: int, text: str, src_lang: str, dest_lang: str, backend, visible: bool):
        super().__init__()
        self.request_id = request_id
        self.text = text
        self.src_lang = src_lang
        self.dest_lang = dest_lang
        self.backend = backend
        self.visible = visible
        self.signals = TranslateSignals()

    def run(self):
        try:
            translated_text = self.backend.translate(self.text, self.src_lang, self.dest_lang)
            self.signals.finished.emit(self.request_id, self.text, translated_text, self.visible)
        except RuntimeError:
            return
        except Exception as exc:
            logger.error("Translation worker failed (request_id=%s): %s", self.request_id, exc, exc_info=True)
            try:
                self.signals.failed.emit(self.request_id, self.text, str(exc), self.visible)
            except RuntimeError:
                return


class BatchTranslateSignals(QObject):
    finished = Signal(list, list)
    failed = Signal(list, str)  # (texts, error message)


class BatchTranslateTask(QRunnable):
    def __init__(self, texts: list[str], src_lang: str, dest_lang: str, backend):
        super().__init__()
        self.texts = texts
        self.src_lang = src_lang
        self.dest_lang = dest_lang
        self.backend = backend
        self.signals = BatchTranslateSignals()

    def run(self):
        try:
            if hasattr(self.backend, "translate_batch"):
                translations = self.backend.translate_batch(self.texts, self.src_lang, self.dest_lang)
            else:
                translations = [self.backend.translate(text, self.src_lang, self.dest_lang) for text in self.texts]
            self.signals.finished.emit(self.texts, translations)
        except RuntimeError:
            return
        except Exception as exc:
            logger.warning("Batch translation failed: %s", exc, exc_info=True)
            try:
                self.signals.failed.emit(self.texts, str(exc))
            except RuntimeError:
                return


class TranslationService(QObject):
    translation_ready = Signal(int, str, str, bool)
    translation_failed = Signal(int, str, str, bool)
    batch_ready = Signal(list, list)
    batch_failed = Signal(str)
    mode_changed = Signal(str)

    def __init__(
        self,
        learning_language: str,
        native_language: str,
        mode: str = "offline",
        thread_pool: QThreadPool | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        # Separate limited pool for background prefetch — caps concurrent HTTP requests
        # to 2 so they don't all start (and timeout) simultaneously, which causes burst
        # signal floods that delay Qt's video frame delivery callbacks.
        self._prefetch_pool = QThreadPool()
        self._prefetch_pool.setMaxThreadCount(2)
        self.learning_language = learning_language
        self.native_language = native_language
        self.translation_mode = mode
        self.translation_cache: dict[tuple[str, str, str], str] = {}
        self._translation_requests: dict[int, dict[str, object]] = {}
        self._translation_requests_by_key: dict[tuple[str, str, str], int] = {}
        self._translation_context_version = 0
        self._next_translation_request_id = 0
        self._online_backend = None
        self._offline_backend = None
        self.prefetch_enabled: bool = True

    def set_languages(self, learning_language: str, native_language: str):
        self.learning_language = learning_language
        self.native_language = native_language
        self.clear_cache()

    def set_mode(self, mode: str):
        self.translation_mode = mode
        self.mode_changed.emit(mode)

    def set_prefetch_enabled(self, enabled: bool):
        self.prefetch_enabled = enabled

    def clear_cache(self):
        self.translation_cache.clear()
        self._translation_context_version += 1
        self._online_backend = None
        if self._offline_backend is not None and hasattr(self._offline_backend, "clear_model_cache"):
            self._offline_backend.clear_model_cache()
        self._offline_backend = None

    def cached_translation(self, text: str) -> str | None:
        return self.translation_cache.get(self._translation_cache_key(text))

    def translate_async(self, text: str, *, visible: bool = True) -> int | None:
        if not text:
            return None
        key = self._translation_cache_key(text)
        cached = self.translation_cache.get(key)
        if cached is not None:
            self.translation_ready.emit(0, text, cached, visible)
            return 0

        existing_request_id = self._translation_requests_by_key.get(key)
        if existing_request_id is not None:
            if visible:
                request = self._translation_requests.get(existing_request_id)
                if request is not None:
                    request["visible"] = True
            return existing_request_id

        self._next_translation_request_id += 1
        request_id = self._next_translation_request_id
        backend = self._get_translation_backend()
        src_lang, dest_lang = self._get_translation_language_codes()
        task = TranslateTask(request_id, text, src_lang, dest_lang, backend, visible)
        self._translation_requests[request_id] = {
            "key": key,
            "visible": visible,
            "context_version": self._translation_context_version,
        }
        self._translation_requests_by_key[key] = request_id
        task.signals.finished.connect(self._on_translation_done)
        task.signals.failed.connect(self._on_translation_failed)
        pool = self._thread_pool if visible else self._prefetch_pool
        pool.start(task)
        return request_id

    def prefetch_async(self, texts: list[str]):
        if not self.prefetch_enabled:
            return
        texts_to_fetch = []
        for text in texts:
            if not text:
                continue
            key = self._translation_cache_key(text)
            if key not in self.translation_cache and key not in self._translation_requests_by_key and text not in texts_to_fetch:
                texts_to_fetch.append(text)
        if not texts_to_fetch:
            return
        if self.translation_mode == "online":
            # googletrans batch API (list input) always fails — use individual tasks directly
            for text in texts_to_fetch:
                self.translate_async(text, visible=False)
            return
        # Offline (MarianMT): genuine batch is efficient
        src_lang, dest_lang = self._get_translation_language_codes()
        task = BatchTranslateTask(texts_to_fetch, src_lang, dest_lang, self._get_translation_backend())
        task.signals.finished.connect(self._on_batch_translation_done)
        task.signals.failed.connect(self._on_batch_translation_failed)
        self._thread_pool.start(task)

    def is_mode_available(self, mode: str) -> bool:
        if mode == "online":
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=2)
            except OSError:
                return False
            backend = self._online_backend if self._online_backend is not None else OnlineTranslationBackend()
            return backend.is_available()
        backend = self._offline_backend if self._offline_backend is not None else MarianMTTranslationBackend()
        return backend.is_available()

    def _translation_cache_key(self, text: str):
        return (self.learning_language, self.native_language, text)

    def _get_translation_language_codes(self):
        if self.translation_mode == "offline":
            return (
                get_marian_language_code(self.learning_language),
                get_marian_language_code(self.native_language),
            )
        return (
            get_google_language_code(self.learning_language),
            get_google_language_code(self.native_language),
        )

    def _get_translation_backend(self):
        if self.translation_mode == "online":
            if self._online_backend is None:
                self._online_backend = OnlineTranslationBackend()
            return self._online_backend
        if self._offline_backend is None:
            self._offline_backend = MarianMTTranslationBackend()
        return self._offline_backend

    def _on_translation_done(self, request_id: int, source_text: str, translated_text: str, visible: bool):
        if request_id:
            request = self._translation_requests.pop(request_id, None)
            if request is None:
                return
            key = request["key"]
            if self._translation_requests_by_key.get(key) == request_id:
                self._translation_requests_by_key.pop(key, None)
            if request["context_version"] != self._translation_context_version:
                return
            self.translation_cache[key] = translated_text
            visible = bool(request["visible"])
        self.translation_ready.emit(request_id, source_text, translated_text, visible)

    def _on_translation_failed(self, request_id: int, source_text: str, error_message: str, visible: bool):
        request = self._translation_requests.pop(request_id, None)
        if request is None:
            return
        key = request["key"]
        if self._translation_requests_by_key.get(key) == request_id:
            self._translation_requests_by_key.pop(key, None)
        if request["context_version"] != self._translation_context_version:
            return
        self.translation_failed.emit(request_id, source_text, error_message, bool(request["visible"]))

    def _on_batch_translation_done(self, texts: list[str], translations: list[str]):
        if len(texts) != len(translations):
            self.batch_failed.emit("Batch translation count mismatch.")
            return
        for text, translation in zip(texts, translations):
            self.translation_cache[self._translation_cache_key(text)] = translation
        self.batch_ready.emit(texts, translations)

    def _on_batch_translation_failed(self, texts: list[str], message: str):
        logger.warning("Batch translation failed, retrying individually: %s", message)
        self.batch_failed.emit(message)
        for text in texts:
            self.translate_async(text, visible=False)
