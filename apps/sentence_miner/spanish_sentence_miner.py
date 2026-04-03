#!/usr/bin/env python3
"""Compatibility CLI for queued-card processing."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from immersion_app.core.anki import DECK_NAME, MODEL_NAME, add_anki_card, test_anki_connection
from immersion_app.core.paths import QUEUE_JSON_PATH as INPUT_FILE, PROCESSED_LOG_PATH as PROCESSED_FILE
from immersion_app.core.queue_store import append_processed_log, load_queue_entries, save_queue_entries


def parse_input_file(filepath=None):
    return load_queue_entries()


def append_to_processed_file(entries):
    append_processed_log(entries)


def rewrite_input_file(entries):
    save_queue_entries(entries)


def main():
    print("=" * 60)
    print("Queued Card Processor")
    print("=" * 60)
    if not test_anki_connection():
        print("AnkiConnect is not available.")
        return

    entries = load_queue_entries()
    if not entries:
        print("No queued entries found.")
        return

    successful_entries = []
    failed_entries = []
    sentence_counts = {}
    for entry in entries:
        sentence = entry["sentence"]
        if sentence in sentence_counts:
            sentence_counts[sentence] += 1
            sentence_for_note = f"{sentence} ({sentence_counts[sentence]})"
        else:
            sentence_counts[sentence] = 1
            sentence_for_note = sentence
        try:
            add_anki_card(sentence_for_note, entry["word"], entry["translation"])
            successful_entries.append(entry)
        except Exception:
            failed_entries.append(entry)

    if successful_entries:
        append_processed_log(successful_entries)
    save_queue_entries(failed_entries)
    print(f"Added: {len(successful_entries)}")
    print(f"Failed: {len(failed_entries)}")


if __name__ == "__main__":
    main()
