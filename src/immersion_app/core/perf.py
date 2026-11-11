"""Opt-in performance spans.

Set ``IMMERSION_PERF=1`` (or the older ``LINGUALOOP_PERF=1``) to record how long named sections take. Each span is
appended as one JSON line to ``<data root>/perf.jsonl``. When the variable is
unset (the default) :func:`perf_span` is a no-op, so it is safe to leave in
hot paths.
"""

from __future__ import annotations

import functools
import json
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

PERF_ENV_VAR = "IMMERSION_PERF"
LEGACY_PERF_ENV_VAR = "LINGUALOOP_PERF"

_lock = threading.Lock()


def perf_enabled() -> bool:
    value = os.environ.get(PERF_ENV_VAR, "").strip() or os.environ.get(LEGACY_PERF_ENV_VAR, "").strip()
    return value.lower() in {"1", "true", "yes", "on"}


def _perf_log_path():
    from immersion_app.core.paths import DATA_ROOT

    return DATA_ROOT / "perf.jsonl"


def record_span(name: str, duration_ms: float, **tags: Any) -> None:
    """Append one span record. Never raises: diagnostics must not break the app."""
    entry = {"ts": time.time(), "name": name, "ms": round(duration_ms, 3), **tags}
    try:
        path = _perf_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except Exception:
        pass


@contextmanager
def perf_span(name: str, **tags: Any) -> Iterator[None]:
    if not perf_enabled():
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        record_span(name, (time.perf_counter() - start) * 1000.0, **tags)


def perf_timed(name: str | None = None) -> Callable:
    """Decorator form of :func:`perf_span`."""

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__qualname__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not perf_enabled():
                return func(*args, **kwargs)
            with perf_span(span_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator
