"""CLI entrypoint for queued-card processing."""

import logging

from immersion_app.core.logging_config import setup_cli_logging
from immersion_app.core.anki import AnkiSettings, add_anki_card, configure_anki, get_anki_settings, test_anki_connection
from immersion_app.core.paths import PROCESSED_LOG_PATH, QUEUE_JSON_PATH
from immersion_app.core.queue_store import append_processed_log, load_queue_entries, save_queue_entries
from immersion_app.core.user_data import load_user_data

logger = logging.getLogger(__name__)


def main():
    setup_cli_logging()
    logger.info("=" * 60)
    logger.info("Queued Card Processor - Starting")
    logger.info("=" * 60)
    logger.info(f"Queue file: {QUEUE_JSON_PATH}")
    # Use the deck/note type chosen in the desktop app's Settings.
    configure_anki(AnkiSettings.from_dict(load_user_data().get("anki")))

    if not test_anki_connection():
        settings = get_anki_settings()
        logger.error(
            f"AnkiConnect is not available, or deck '{settings.deck_name}' / note type "
            f"'{settings.note_type}' is missing (choose them in Language Immersion Tools's Settings)"
        )
        return 1

    entries = load_queue_entries()
    if not entries:
        logger.info("No queued entries found")
        return 0

    logger.info(f"Processing {len(entries)} queued entries")
    successful_entries = []
    failed_entries = []
    sentence_counts = {}
    for idx, entry in enumerate(entries, 1):
        sentence = entry["sentence"]
        if sentence in sentence_counts:
            sentence_counts[sentence] += 1
            sentence_for_note = f"{sentence} ({sentence_counts[sentence]})"
        else:
            sentence_counts[sentence] = 1
            sentence_for_note = sentence
        try:
            logger.debug(f"Processing entry {idx}/{len(entries)}: word='{entry['word']}'")
            add_anki_card(sentence_for_note, entry["word"], entry["translation"])
            successful_entries.append(entry)
        except Exception as e:
            logger.error(f"Failed to add card for word '{entry['word']}': {e}", exc_info=True)
            failed_entries.append(entry)

    if successful_entries:
        append_processed_log(successful_entries)

    save_queue_entries(failed_entries)
    logger.info(f"Processing complete: {len(successful_entries)} added, {len(failed_entries)} failed")
    logger.info(f"Processed log: {PROCESSED_LOG_PATH}")
    return 0 if not failed_entries else 1


if __name__ == "__main__":
    raise SystemExit(main())
