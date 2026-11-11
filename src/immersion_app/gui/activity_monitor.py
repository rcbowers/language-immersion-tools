"""Application-wide user-input monitor for usage time tracking.

Installed as an event filter on the QApplication, it turns real user input
(clicks, mouse movement, scrolling, key presses) in any of the app's windows
into a throttled ``activity`` signal. Background work (translation prefetch,
selection clears, page renders) never reaches it, so it cannot mark the user
active on its own.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject, Signal

DEFAULT_THROTTLE_SECONDS = 5.0

_INPUT_EVENT_TYPES = frozenset(
    {
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonDblClick,
        QEvent.Type.MouseMove,
        QEvent.Type.Wheel,
        QEvent.Type.KeyPress,
        QEvent.Type.TouchBegin,
    }
)


class UserActivityMonitor(QObject):
    """Emit ``activity`` at most once per ``throttle_seconds`` while the user provides input."""

    activity = Signal()

    def __init__(self, throttle_seconds: float = DEFAULT_THROTTLE_SECONDS, clock=time.monotonic, parent: QObject | None = None):
        super().__init__(parent)
        self._throttle_seconds = throttle_seconds
        self._clock = clock
        self._last_emit: float | None = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt API)
        if event.type() in _INPUT_EVENT_TYPES:
            self.notify_input()
        return False  # never consume events

    def notify_input(self) -> None:
        now = self._clock()
        if self._last_emit is None or now - self._last_emit >= self._throttle_seconds:
            self._last_emit = now
            self.activity.emit()
