"""CLI entrypoint for queued-card processing."""

from immersion_app.core.anki import add_anki_card, test_anki_connection
from immersion_app.core.paths import PROCESSED_LOG_PATH, QUEUE_JSON_PATH
from immersion_app.core.queue_store import append_processed_log, load_queue_entries, save_queue_entries


def main():
    print("=" * 60)
    print("Queued Card Processor")
    print("=" * 60)
    print(f"Queue file: {QUEUE_JSON_PATH}")
    if not test_anki_connection():
        print("AnkiConnect is not available.")
        return 1

    entries = load_queue_entries()
    if not entries:
        print("No queued entries found.")
        return 0

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
    print(f"Processed log: {PROCESSED_LOG_PATH}")
    return 0 if not failed_entries else 1


if __name__ == "__main__":
    raise SystemExit(main())
