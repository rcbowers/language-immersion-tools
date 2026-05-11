"""Structured queue storage with legacy txt import fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from .paths import (
    LEGACY_PROCESSED_PATH,
    LEGACY_QUEUE_PATH,
    PROCESSED_LOG_PATH,
    QUEUE_JSON_PATH,
    ensure_runtime_dirs,
)


def _read_legacy_queue_entries(path):
    if not path.exists():
        return []

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []

    entries = []
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        if index + 2 >= len(lines):
            break
        sentence = lines[index].strip()
        word = lines[index + 1].strip()
        translation = lines[index + 2].strip()
        if sentence and word and translation:
            entries.append(
                {
                    "sentence": sentence,
                    "word": word,
                    "translation": translation,
                    "source_name": "legacy-import",
                    "source_type": "unknown",
                    "location": "",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "status": "queued",
                }
            )
        index += 3
    return entries


def load_queue_entries():
    ensure_runtime_dirs()
    if QUEUE_JSON_PATH.exists():
        try:
            logger.debug(f"Loading queue from {QUEUE_JSON_PATH}")
            loaded = json.loads(QUEUE_JSON_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = [entry for entry in loaded if isinstance(entry, dict)]
                logger.info(f"Loaded {len(entries)} queue entries from JSON")
                return entries
        except Exception as e:
            logger.warning(f"Failed to load queue from JSON: {e}, trying legacy format")

    # Try legacy format
    legacy_entries = _read_legacy_queue_entries(LEGACY_QUEUE_PATH)
    if legacy_entries:
        logger.warning(f"Loaded {len(legacy_entries)} entries from legacy queue format at {LEGACY_QUEUE_PATH}")
    else:
        logger.debug("No queue entries found")
    return legacy_entries


def save_queue_entries(entries):
    ensure_runtime_dirs()
    logger.info(f"Saving {len(entries)} queue entries to {QUEUE_JSON_PATH}")
    temp_path = QUEUE_JSON_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(QUEUE_JSON_PATH)
    logger.debug("Queue saved successfully")


def append_queue_entry(entry):
    entries = load_queue_entries()
    entries.append(entry)
    save_queue_entries(entries)


def queue_count():
    return len(load_queue_entries())


def append_processed_log(entries):
    ensure_runtime_dirs()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"Appending {len(entries)} processed entries to log at {timestamp}")

    with PROCESSED_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"\n{'=' * 60}\n")
        handle.write(f"Batch processed on: {timestamp}\n")
        handle.write(f"{'=' * 60}\n\n")
        for entry in entries:
            handle.write(
                f"[{timestamp}] {entry['word']} - {entry['translation']} | "
                f"{entry.get('source_name', 'unknown')} | {entry.get('location', '')}\n"
            )
            handle.write(f"  Sentence: {entry['sentence']}\n\n")

    if LEGACY_PROCESSED_PATH.exists():
        logger.debug(f"Also appending to legacy processed log at {LEGACY_PROCESSED_PATH}")
        with LEGACY_PROCESSED_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"\n{'=' * 60}\n")
            handle.write(f"Batch processed on: {timestamp}\n")
            handle.write(f"{'=' * 60}\n\n")
            for entry in entries:
                handle.write(f"[{timestamp}] {entry['word']} - {entry['translation']}\n")
                handle.write(f"  Sentence: {entry['sentence']}\n\n")

    logger.debug("Processed log updated successfully")
