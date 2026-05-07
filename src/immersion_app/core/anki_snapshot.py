"""Persistent snapshot of the Anki deck's vocabulary for offline word highlighting."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .anki import DECK_NAME
from .paths import ANKI_SNAPSHOT_PATH


def load_snapshot() -> set[str]:
    try:
        data = json.loads(ANKI_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        return set(data.get("words", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_snapshot(words: set[str]) -> None:
    ANKI_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ANKI_SNAPSHOT_PATH.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "deck": DECK_NAME,
                "words": sorted(words),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
