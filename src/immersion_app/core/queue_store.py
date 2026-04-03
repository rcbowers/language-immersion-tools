"""Structured queue storage with legacy txt import fallback."""

from __future__ import annotations

import json
from datetime import datetime

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
            loaded = json.loads(QUEUE_JSON_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                return [entry for entry in loaded if isinstance(entry, dict)]
        except Exception:
            pass
    return _read_legacy_queue_entries(LEGACY_QUEUE_PATH)


def save_queue_entries(entries):
    ensure_runtime_dirs()
    temp_path = QUEUE_JSON_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(QUEUE_JSON_PATH)


def append_queue_entry(entry):
    entries = load_queue_entries()
    entries.append(entry)
    save_queue_entries(entries)


def queue_count():
    return len(load_queue_entries())


def append_processed_log(entries):
    ensure_runtime_dirs()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        with LEGACY_PROCESSED_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"\n{'=' * 60}\n")
            handle.write(f"Batch processed on: {timestamp}\n")
            handle.write(f"{'=' * 60}\n\n")
            for entry in entries:
                handle.write(f"[{timestamp}] {entry['word']} - {entry['translation']}\n")
                handle.write(f"  Sentence: {entry['sentence']}\n\n")
