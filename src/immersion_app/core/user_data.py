"""Persistent user state for the unified workspace."""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

from .language_config import DEFAULT_LEARNING_LANGUAGE, DEFAULT_NATIVE_LANGUAGE, normalize_language_code
from .paths import LEGACY_USER_STATE_PATH, USER_STATE_PATH, ensure_runtime_dirs


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
        },
        "last_session": {
            "content_type": "",
            "pdf_path": "",
            "page_index": 0,
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
        "theme_mode": "dark" if str(preferences.get("theme_mode") or "").strip().lower() == "dark" else "light",
    }
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
    ensure_runtime_dirs()
    logger.info(f"Saving user data to {USER_STATE_PATH}")
    logger.debug(
        f"Save summary: cards_added={payload.get('analytics', {}).get('cards_added_total', 0)}, "
        f"vocabulary_count={len(payload.get('analytics', {}).get('vocabulary_seen', []))}"
    )
    temp_path = USER_STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, USER_STATE_PATH)
    logger.debug("User data saved successfully")
