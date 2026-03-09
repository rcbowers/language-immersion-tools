#!/usr/bin/env python3
"""Language configuration for sentence miner GUI."""

from __future__ import annotations


SUPPORTED_LANGUAGES = {
    "es": {"label": "Spanish", "google": "es", "argos": "es", "whisper": "es"},
    "ja": {"label": "Japanese", "google": "ja", "argos": "ja", "whisper": "ja"},
    "zh": {"label": "Chinese", "google": "zh-cn", "argos": "zh", "whisper": "zh"},
    "it": {"label": "Italian", "google": "it", "argos": "it", "whisper": "it"},
    "fr": {"label": "French", "google": "fr", "argos": "fr", "whisper": "fr"},
    "en": {"label": "English", "google": "en", "argos": "en", "whisper": "en"},
}

DEFAULT_LEARNING_LANGUAGE = "es"
DEFAULT_NATIVE_LANGUAGE = "en"


def normalize_language_code(code: str | None, default: str) -> str:
    value = (code or "").strip().lower()
    return value if value in SUPPORTED_LANGUAGES else default


def list_language_codes() -> list[str]:
    return list(SUPPORTED_LANGUAGES.keys())


def get_language_label(code: str) -> str:
    return SUPPORTED_LANGUAGES[code]["label"]


def get_google_language_code(code: str) -> str:
    return SUPPORTED_LANGUAGES[code]["google"]


def get_argos_language_code(code: str) -> str:
    return SUPPORTED_LANGUAGES[code]["argos"]


def get_whisper_language_code(code: str) -> str:
    return SUPPORTED_LANGUAGES[code]["whisper"]
