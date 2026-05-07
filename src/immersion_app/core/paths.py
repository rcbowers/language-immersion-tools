"""Project and runtime data paths."""

from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT.parent
PROJECT_ROOT = SRC_ROOT.parent
DATA_ROOT = PROJECT_ROOT / "data"
QUEUE_DIR = DATA_ROOT / "queue"
LOG_DIR = DATA_ROOT / "logs"
STATE_DIR = DATA_ROOT / "state"

QUEUE_JSON_PATH = QUEUE_DIR / "queued_cards.json"
PROCESSED_LOG_PATH = LOG_DIR / "processed_cards.log"
USER_STATE_PATH = STATE_DIR / "sentence_miner_user_data.json"
ANKI_SNAPSHOT_PATH = STATE_DIR / "anki_snapshot.json"

LEGACY_QUEUE_PATH = PROJECT_ROOT / "words_to_process.txt"
LEGACY_PROCESSED_PATH = PROJECT_ROOT / "processed_words.txt"
LEGACY_USER_STATE_PATH = PROJECT_ROOT / "sentence_miner_user_data.json"


def ensure_runtime_dirs() -> None:
    for path in (QUEUE_DIR, LOG_DIR, STATE_DIR):
        path.mkdir(parents=True, exist_ok=True)

