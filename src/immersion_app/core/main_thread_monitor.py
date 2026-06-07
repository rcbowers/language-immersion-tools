"""Diagnostic tool to detect main thread stalls."""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)


class MainThreadBlockDetector(QObject):
    """QTimer-based heartbeat that warns when the main thread is stalled.

    Threshold levels:
      >=100 ms  → DEBUG  (visible jitter)
      >=250 ms  → WARNING (noticeable hitch)
      >=1000 ms → ERROR   (hard freeze)
    """

    def __init__(self, warn_threshold_ms: int = 100, parent: QObject | None = None):
        super().__init__(parent)
        self._threshold = warn_threshold_ms / 1000.0
        self._last_tick = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.setInterval(100)  # tighter poll so short stalls aren't missed
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._last_tick = time.perf_counter()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _tick(self):
        now = time.perf_counter()
        elapsed = now - self._last_tick
        self._last_tick = now
        if elapsed < self._threshold:
            return
        ms = elapsed * 1000
        if ms >= 1000:
            logger.error("[HEARTBEAT] Main thread HARD FREEZE %.0fms", ms)
        elif ms >= 250:
            logger.warning("[HEARTBEAT] Main thread stalled %.0fms", ms)
        else:
            logger.debug("[HEARTBEAT] Main thread hitch %.0fms", ms)
