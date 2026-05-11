"""Persistent snapshot of the Anki deck's vocabulary for offline word highlighting."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from .anki import DECK_NAME
from .paths import ANKI_SNAPSHOT_PATH


def load_snapshot() -> set[str]:
    try:
        logger.debug(f"Loading Anki snapshot from {ANKI_SNAPSHOT_PATH}")
        data = json.loads(ANKI_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        words = set(data.get("words", []))
        updated_at = data.get("updated_at", "unknown")
        logger.info(f"Loaded Anki snapshot: {len(words)} words (updated: {updated_at})")
        return words
    except FileNotFoundError:
        logger.info(f"No Anki snapshot found at {ANKI_SNAPSHOT_PATH}")
        return set()
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Anki snapshot JSON: {e}")
        return set()


def save_snapshot(words: set[str]) -> None:
    logger.info(f"Saving Anki snapshot: {len(words)} words to {ANKI_SNAPSHOT_PATH}")
    ANKI_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    ANKI_SNAPSHOT_PATH.write_text(
        json.dumps(
            {
                "updated_at": timestamp,
                "deck": DECK_NAME,
                "words": sorted(words),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.debug(f"Anki snapshot saved successfully at {timestamp}")
