"""Small helpers for Qt signals emitted from worker threads."""

from __future__ import annotations


def safe_emit(signal, *args) -> bool:
    """Emit ``signal`` from a worker, ignoring the case where its receiver was already destroyed.

    PySide raises ``RuntimeError`` when a signal's owning QObject has been
    deleted (e.g. the window closed while a worker was running). Only that
    emit is guarded here, so genuine errors raised by the work itself are
    never swallowed. Returns False if the emit was skipped.
    """
    try:
        signal.emit(*args)
    except RuntimeError:
        return False
    return True
