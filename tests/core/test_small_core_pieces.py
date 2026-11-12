"""Small core helpers: shortcut groups, safe_emit, main-thread stall detector, logging setup."""

from __future__ import annotations

import logging

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction

from immersion_app.core import logging_config, main_thread_monitor
from immersion_app.core.mode import WorkspaceMode
from immersion_app.core.shortcuts import ShortcutManager
from immersion_app.core.signals import safe_emit


# --- shortcuts -----------------------------------------------------------


@pytest.fixture
def shortcuts(qapp):
    manager = ShortcutManager()
    actions = {}
    for group in ("global", "pdf", "video"):
        actions[group] = QAction(group)
        manager.add_shortcut(group, actions[group])
    return manager, actions


@pytest.mark.parametrize(
    "mode, enabled",
    [
        (WorkspaceMode.WELCOME, {"global": True, "pdf": False, "video": False}),
        (WorkspaceMode.PDF, {"global": True, "pdf": True, "video": False}),
        (WorkspaceMode.VIDEO, {"global": True, "pdf": False, "video": True}),
    ],
)
def test_update_for_mode_enables_only_matching_group(shortcuts, mode, enabled):
    manager, actions = shortcuts
    manager.update_for_mode(mode)
    assert {name: action.isEnabled() for name, action in actions.items()} == enabled


def test_switching_modes_reenables_and_disables(shortcuts):
    manager, actions = shortcuts
    manager.update_for_mode(WorkspaceMode.PDF)
    manager.update_for_mode(WorkspaceMode.VIDEO)
    assert actions["video"].isEnabled() and not actions["pdf"].isEnabled()
    manager.update_for_mode(WorkspaceMode.WELCOME)
    assert not actions["video"].isEnabled() and actions["global"].isEnabled()


def test_unknown_shortcut_group_rejected(qapp):
    with pytest.raises(ValueError, match="Unknown shortcut group"):
        ShortcutManager().add_shortcut("audio", QAction("x"))


# --- safe_emit -----------------------------------------------------------


class _Emitter(QObject):
    ping = Signal(int)


def test_safe_emit_delivers(qapp):
    emitter = _Emitter()
    seen = []
    emitter.ping.connect(seen.append)
    assert safe_emit(emitter.ping, 5) is True
    assert seen == [5]


def test_safe_emit_swallows_runtime_error_from_deleted_receiver():
    class _Dead:
        def emit(self, *args):
            raise RuntimeError("Internal C++ object (_Emitter) already deleted.")

    assert safe_emit(_Dead(), 1) is False


def test_safe_emit_does_not_swallow_other_errors():
    class _Broken:
        def emit(self, *args):
            raise ValueError("real bug")

    with pytest.raises(ValueError):
        safe_emit(_Broken(), 1)


def test_safe_emit_with_really_deleted_qobject(qapp):
    import shiboken6

    emitter = _Emitter()
    signal = emitter.ping
    shiboken6.delete(emitter)
    assert safe_emit(signal, 1) is False


# --- main thread monitor -------------------------------------------------


@pytest.fixture
def monitor(qapp, monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr(main_thread_monitor.time, "perf_counter", lambda: clock["now"])
    detector = main_thread_monitor.MainThreadBlockDetector(warn_threshold_ms=100)
    return detector, clock


def _tick_after(detector, clock, seconds):
    clock["now"] += seconds
    detector._tick()


def test_no_report_under_threshold(monitor, caplog):
    detector, clock = monitor
    with caplog.at_level(logging.DEBUG, logger=main_thread_monitor.logger.name):
        _tick_after(detector, clock, 0.099)
    assert caplog.records == []


@pytest.mark.parametrize(
    "stall_s, level, text",
    [
        (0.125, logging.DEBUG, "hitch"),
        (0.2, logging.DEBUG, "hitch"),
        (0.25, logging.WARNING, "stalled"),
        (0.5, logging.WARNING, "stalled"),
        (1.0, logging.ERROR, "HARD FREEZE"),
        (5.0, logging.ERROR, "HARD FREEZE"),
    ],
)
def test_stall_levels(monitor, caplog, stall_s, level, text):
    detector, clock = monitor
    with caplog.at_level(logging.DEBUG, logger=main_thread_monitor.logger.name):
        _tick_after(detector, clock, stall_s)
    assert [(r.levelno, text in r.getMessage()) for r in caplog.records] == [(level, True)]


def test_tick_resets_the_baseline(monitor, caplog):
    detector, clock = monitor
    with caplog.at_level(logging.DEBUG, logger=main_thread_monitor.logger.name):
        _tick_after(detector, clock, 2.0)
        caplog.clear()
        _tick_after(detector, clock, 0.05)
    assert caplog.records == []


def test_start_and_stop_control_timer(monitor):
    detector, clock = monitor
    detector.start()
    assert detector._timer.isActive()
    detector.stop()
    assert not detector._timer.isActive()


# --- logging config ------------------------------------------------------


@pytest.fixture
def isolated_logging(tmp_path, monkeypatch):
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    monkeypatch.setattr(logging_config, "LOG_DIR", tmp_path / "logs")
    yield tmp_path / "logs"
    for handler in list(root.handlers):
        handler.close()
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])


def test_setup_logging_is_idempotent(isolated_logging):
    logging_config.setup_logging()
    logging_config.setup_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 2  # one file, one stream: no duplicates after reconfiguration
    assert sum(isinstance(h, logging.FileHandler) for h in root.handlers) == 1


def test_setup_logging_creates_timestamped_session_file(isolated_logging):
    path = logging_config.setup_logging()
    assert path.parent == isolated_logging and path.exists()
    assert path.name.startswith("session_") and path.suffix == ".log"


def test_cli_logging_uses_cli_prefix_and_requested_level(isolated_logging):
    path = logging_config.setup_cli_logging(level=logging.WARNING)
    assert path.name.startswith("cli_")
    assert logging.getLogger().level == logging.WARNING


def test_noisy_third_party_loggers_are_quieted(isolated_logging):
    logging.getLogger("httpx").setLevel(logging.DEBUG)
    logging_config.setup_logging()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("urllib3").level == logging.WARNING


def test_get_logger_returns_named_logger():
    assert logging_config.get_logger("immersion.test") is logging.getLogger("immersion.test")
