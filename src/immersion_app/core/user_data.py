"""Persistent user state for the unified workspace."""

from __future__ import annotations

import json
import os

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
            "vocabulary_seen": [],
        },
        "recent_files": [],
    }


def load_user_data():
    payload = default_user_data()
    for path in (USER_STATE_PATH, LEGACY_USER_STATE_PATH):
        if not path.exists():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(loaded, dict):
            continue
        payload.update(loaded)
        break

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
    }
    payload["analytics"] = payload.get("analytics") or {"cards_added_total": 0, "vocabulary_seen": []}
    payload["last_session"] = payload.get("last_session") or default_user_data()["last_session"]
    payload["workspace"] = payload.get("workspace") or {"current_view": "welcome"}
    payload["recent_files"] = payload.get("recent_files") or []
    return payload


def save_user_data(payload):
    ensure_runtime_dirs()
    temp_path = USER_STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, USER_STATE_PATH)
