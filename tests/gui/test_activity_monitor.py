"""Tests for the application-wide user activity monitor."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject

from immersion_app.gui.activity_monitor import UserActivityMonitor


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _event(event_type):
    return QEvent(event_type)


def test_input_events_emit_activity(qapp):
    clock = FakeClock()
    monitor = UserActivityMonitor(throttle_seconds=5, clock=clock)
    hits = []
    monitor.activity.connect(lambda: hits.append(clock.now))

    assert monitor.eventFilter(QObject(), _event(QEvent.Type.KeyPress)) is False
    assert hits == [1000.0]


def test_activity_is_throttled(qapp):
    clock = FakeClock()
    monitor = UserActivityMonitor(throttle_seconds=5, clock=clock)
    hits = []
    monitor.activity.connect(lambda: hits.append(clock.now))

    for offset in (0, 1, 2, 4.9, 5, 6, 10.5):
        clock.now = 1000.0 + offset
        monitor.eventFilter(QObject(), _event(QEvent.Type.Wheel))

    assert hits == [1000.0, 1005.0, 1010.5]


def test_non_input_events_are_ignored(qapp):
    monitor = UserActivityMonitor(throttle_seconds=0, clock=FakeClock())
    hits = []
    monitor.activity.connect(lambda: hits.append(True))

    for event_type in (QEvent.Type.Paint, QEvent.Type.Timer, QEvent.Type.Resize, QEvent.Type.UpdateRequest):
        monitor.eventFilter(QObject(), _event(event_type))

    assert hits == []
