"""Project and runtime data paths.

Runtime data (user state, queue, logs, previews) lives in a per-user data
folder, never inside the source tree or install directory:

* Windows: ``%APPDATA%\\LanguageImmersionTools``
* macOS:   ``~/Library/Application Support/LanguageImmersionTools``
* Linux:   ``~/.local/share/LanguageImmersionTools``

Set the ``IMMERSION_DATA_DIR`` environment variable to use a different folder
(used by the test suite and for portable installs). The old
``LINGUALOOP_DATA_DIR`` name is still honored as a fallback.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from platformdirs import user_data_dir

logger = logging.getLogger(__name__)

APP_NAME = "LanguageImmersionTools"
DATA_DIR_ENV_VAR = "IMMERSION_DATA_DIR"
# Names used before the rebrand from LinguaLoop; kept so existing installs keep working.
LEGACY_APP_NAME = "LinguaLoop"
LEGACY_DATA_DIR_ENV_VAR = "LINGUALOOP_DATA_DIR"

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PACKAGE_ROOT.parent
PROJECT_ROOT = SRC_ROOT.parent


def resolve_data_root() -> Path:
    override = (
        os.environ.get(DATA_DIR_ENV_VAR, "").strip()
        or os.environ.get(LEGACY_DATA_DIR_ENV_VAR, "").strip()
    )
    if override:
        return Path(override).expanduser()
    return Path(user_data_dir(APP_NAME, appauthor=False, roaming=True))


DATA_ROOT = resolve_data_root()
QUEUE_DIR = DATA_ROOT / "queue"
LOG_DIR = DATA_ROOT / "logs"
STATE_DIR = DATA_ROOT / "state"
PREVIEW_DIR = DATA_ROOT / "previews"

QUEUE_JSON_PATH = QUEUE_DIR / "queued_cards.json"
PROCESSED_LOG_PATH = LOG_DIR / "processed_cards.log"
USER_STATE_PATH = STATE_DIR / "sentence_miner_user_data.json"
ANKI_SNAPSHOT_PATH = STATE_DIR / "anki_snapshot.json"
AUTOMINE_RECENT_SOURCES_PATH = STATE_DIR / "automine_recent_sources.json"

# Pre-1.0 source checkouts kept runtime data in ``<repo>/data``. When running
# from source we migrate it once; frozen builds never had it.
LEGACY_DATA_ROOT = PROJECT_ROOT / "data"
LEGACY_QUEUE_PATH = PROJECT_ROOT / "words_to_process.txt"
LEGACY_PROCESSED_PATH = PROJECT_ROOT / "processed_words.txt"
LEGACY_USER_STATE_PATH = PROJECT_ROOT / "sentence_miner_user_data.json"


def ensure_runtime_dirs() -> None:
    for path in (QUEUE_DIR, LOG_DIR, STATE_DIR, PREVIEW_DIR):
        path.mkdir(parents=True, exist_ok=True)


def migrate_legacy_appname_data(old_root: Path | None = None, data_root: Path | None = None) -> bool:
    """Copy the pre-rebrand ``LinguaLoop`` data folder into the new one once.

    Only runs when the new folder has no user state yet, so it never overwrites
    newer data. Skipped when a data-dir environment override is set. The old
    folder is left in place. Returns True if data was copied.
    """
    if old_root is None:
        if os.environ.get(DATA_DIR_ENV_VAR, "").strip() or os.environ.get(LEGACY_DATA_DIR_ENV_VAR, "").strip():
            return False
        old_root = Path(user_data_dir(LEGACY_APP_NAME, appauthor=False, roaming=True))
    data_root = DATA_ROOT if data_root is None else data_root
    try:
        if old_root.resolve() == data_root.resolve():
            return False
    except OSError:
        return False
    if not old_root.is_dir() or (data_root / "state" / USER_STATE_PATH.name).exists():
        return False
    try:
        shutil.copytree(old_root, data_root, dirs_exist_ok=True)
    except OSError as exc:
        logger.warning("Could not migrate data from %s: %s", old_root, exc)
        return False
    logger.info("Migrated data from %s to %s", old_root, data_root)
    return True


def migrate_legacy_data(legacy_root: Path | None = None, data_root: Path | None = None) -> bool:
    """Copy ``<repo>/data`` into the per-user data folder once.

    Only runs when the new folder has no user state yet, so it never overwrites
    newer data. The legacy folder is left in place. Returns True if data was copied.
    """
    legacy_root = LEGACY_DATA_ROOT if legacy_root is None else legacy_root
    data_root = DATA_ROOT if data_root is None else data_root
    if getattr(sys, "frozen", False):
        return False
    try:
        if legacy_root.resolve() == data_root.resolve():
            return False
    except OSError:
        return False
    legacy_state = legacy_root / "state"
    new_state_file = data_root / "state" / USER_STATE_PATH.name
    if not legacy_state.is_dir() or new_state_file.exists():
        return False
    try:
        for sub in ("state", "queue", "logs"):
            source = legacy_root / sub
            if source.is_dir():
                shutil.copytree(source, data_root / sub, dirs_exist_ok=True)
    except OSError as exc:
        logger.warning("Could not migrate legacy data from %s: %s", legacy_root, exc)
        return False
    logger.info("Migrated legacy data from %s to %s", legacy_root, data_root)
    return True
