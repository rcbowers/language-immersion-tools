"""Persistent user state for the unified workspace."""

from __future__ import annotations

import copy
import json
import logging
import os

from PySide6.QtCore import QRunnable, QThreadPool

from .anki import AnkiSettings
from .appearance_manager import AppearanceManager
from .language_config import DEFAULT_LEARNING_LANGUAGE, DEFAULT_NATIVE_LANGUAGE, normalize_language_code
from .paths import LEGACY_USER_STATE_PATH, USER_STATE_PATH

logger = logging.getLogger(__name__)


# Saves run on a dedicated single-thread pool so they complete in the order
# they were requested (a newer snapshot can never be overwritten by an older
# one) and can be flushed on exit.
_SAVE_POOL = QThreadPool()
_SAVE_POOL.setMaxThreadCount(1)


def _write_snapshot(snapshot: dict) -> None:
    import time as _time
    t0 = _time.perf_counter()
    json_text = json.dumps(snapshot, ensure_ascii=False, indent=2)
    json_ms = (_time.perf_counter() - t0) * 1000
    size_kb = len(json_text) / 1024
    if json_ms >= 50:
        logger.warning("[SAVE-WORKER] json.dumps %.1fms | %.1f KB", json_ms, size_kb)
    else:
        logger.debug("[SAVE-WORKER] json.dumps %.1fms | %.1f KB", json_ms, size_kb)
    USER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = USER_STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json_text, encoding="utf-8")
    os.replace(temp_path, USER_STATE_PATH)
    logger.debug("User data saved successfully")


class _SaveWorker(QRunnable):
    def __init__(self, snapshot: dict):
        super().__init__()
        self._snapshot = snapshot

    def run(self):
        try:
            _write_snapshot(self._snapshot)
        except Exception as exc:
            logger.error("Background save failed: %s", exc)


def flush_user_data(payload: dict | None = None, timeout_ms: int = 5000) -> None:
    """Wait for pending background saves; if ``payload`` is given, write it synchronously last.

    Call on shutdown so the final state (e.g. the last study session) is not lost.
    """
    _SAVE_POOL.waitForDone(timeout_ms)
    if payload is not None:
        try:
            _write_snapshot(copy.deepcopy(payload))
        except Exception as exc:
            logger.error("Final save failed: %s", exc)


def default_user_data():
    return {
        "version": 2,
        "workspace": {
            "current_view": "welcome",
        },
        "preferences": {
            "learning_language": DEFAULT_LEARNING_LANGUAGE,
            "native_language": DEFAULT_NATIVE_LANGUAGE,
            "translation_mode": "online",
            "video_playback_speed": 1.0,
            "theme_mode": "light",
            "prefetch_enabled": True,
        },
        "anki": AnkiSettings().to_dict(),
        "onboarding": {
            "dismissed": False,
        },
        "last_session": {
            "content_type": "",
            "pdf_path": "",
            "page_index": 0,
            "chapter": None,
            "chapter_page": None,
            "video_path": "",
            "video_position_ms": 0,
            "srt_path": "",
            "subtitle_offset_ms": 0,
        },
        "analytics": {
            "cards_added_total": 0,
            "cards_added_by_day": {},
            "vocabulary_seen": [],
        },
        "recent_files": [],
        "progress": {
            "completed_pages": {},
            "completed_videos": {},
        },
        "usage_time": {
            "sessions": [],
            "total_seconds": 0,
            "last_activity_timestamp": "",
        },
    }


def load_user_data():
    payload = default_user_data()
    loaded_from = None
    for path in (USER_STATE_PATH, LEGACY_USER_STATE_PATH):
        if not path.exists():
            continue
        try:
            logger.debug(f"Loading user data from {path}")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load user data from {path}: {e}")
            continue
        if not isinstance(loaded, dict):
            logger.warning(f"Invalid user data format in {path}, expected dict")
            continue
        payload.update(loaded)
        loaded_from = path
        break

    if loaded_from:
        logger.info(f"User data loaded from {loaded_from}")
    else:
        logger.info("No existing user data found, using defaults")

    preferences = payload.get("preferences") or {}
    payload["preferences"] = {
        "learning_language": normalize_language_code(
            preferences.get("learning_language"), DEFAULT_LEARNING_LANGUAGE
        ),
        "native_language": normalize_language_code(
            preferences.get("native_language"), DEFAULT_NATIVE_LANGUAGE
        ),
        "translation_mode": str(preferences.get("translation_mode") or "online"),
        "video_playback_speed": float(preferences.get("video_playback_speed") or 1.0),
        "theme_mode": AppearanceManager.normalize_mode(preferences.get("theme_mode")).value,
        "prefetch_enabled": bool(preferences.get("prefetch_enabled", True)),
    }
    payload["anki"] = AnkiSettings.from_dict(payload.get("anki")).to_dict()
    onboarding = payload.get("onboarding") if isinstance(payload.get("onboarding"), dict) else {}
    payload["onboarding"] = {"dismissed": bool(onboarding.get("dismissed", False))}
    payload["analytics"] = payload.get("analytics") or {
        "cards_added_total": 0,
        "cards_added_by_day": {},
        "vocabulary_seen": [],
    }
    payload["analytics"]["cards_added_total"] = int(payload["analytics"].get("cards_added_total") or 0)
    daily_counts = payload["analytics"].get("cards_added_by_day")
    payload["analytics"]["cards_added_by_day"] = daily_counts if isinstance(daily_counts, dict) else {}
    vocabulary_seen = payload["analytics"].get("vocabulary_seen")
    payload["analytics"]["vocabulary_seen"] = vocabulary_seen if isinstance(vocabulary_seen, list) else []
    payload["last_session"] = payload.get("last_session") or default_user_data()["last_session"]
    payload["workspace"] = payload.get("workspace") or {"current_view": "welcome"}
    payload["recent_files"] = payload.get("recent_files") or []

    # Ensure progress section exists
    progress = payload.get("progress") or {}
    payload["progress"] = {
        "completed_pages": progress.get("completed_pages") if isinstance(progress.get("completed_pages"), dict) else {},
        "completed_videos": progress.get("completed_videos") if isinstance(progress.get("completed_videos"), dict) else {},
    }

    # Ensure usage_time section exists
    usage_time = payload.get("usage_time") or {}
    payload["usage_time"] = {
        "sessions": usage_time.get("sessions") if isinstance(usage_time.get("sessions"), list) else [],
        "total_seconds": int(usage_time.get("total_seconds") or 0),
        "last_activity_timestamp": str(usage_time.get("last_activity_timestamp") or ""),
    }

    # Log key configuration
    logger.info(
        f"Configuration: learning={payload['preferences']['learning_language']}, "
        f"native={payload['preferences']['native_language']}, "
        f"translation_mode={payload['preferences']['translation_mode']}, "
        f"theme_mode={payload['preferences']['theme_mode']}"
    )
    logger.debug(
        f"Analytics: cards_added={payload['analytics']['cards_added_total']}, "
        f"vocabulary_count={len(payload['analytics']['vocabulary_seen'])}"
    )

    return payload


def save_user_data(payload):
    import time as _time
    # No directory setup here: the save worker creates the state folder, keeping disk I/O off the UI thread.
    vocab_len = len(payload.get("analytics", {}).get("vocabulary_seen", []))
    sessions_len = len(payload.get("usage_time", {}).get("sessions", []))
    t0 = _time.perf_counter()
    snapshot = copy.deepcopy(payload)
    deepcopy_ms = (_time.perf_counter() - t0) * 1000
    if deepcopy_ms >= 20:
        logger.warning(
            "[SAVE] deepcopy %.1fms | vocab=%d sessions=%d",
            deepcopy_ms, vocab_len, sessions_len,
        )
    else:
        logger.debug(
            "[SAVE] deepcopy %.1fms | vocab=%d sessions=%d",
            deepcopy_ms, vocab_len, sessions_len,
        )
    _SAVE_POOL.start(_SaveWorker(snapshot))
