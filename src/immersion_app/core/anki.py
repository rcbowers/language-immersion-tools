"""AnkiConnect helpers for the immersion app."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


DECK_NAME = "2025 Spanish Immersion"
MODEL_NAME = "Basic"
ANKI_CONNECT_URL = "http://localhost:8765"
DEFAULT_ANKI_PATH = r"%LOCALAPPDATA%\Programs\Anki\anki.exe"
ANKI_STARTUP_TIMEOUT_SECONDS = 20.0
ANKI_STARTUP_POLL_SECONDS = 0.5


def start_anki_if_needed() -> bool:
    """Start Anki when neither AnkiConnect nor an Anki process is available.

    Returns ``True`` only if this call launched Anki.  A running Anki process is
    left alone even when AnkiConnect is unavailable, so an extension/configuration
    issue is reported by the usual connection check instead of launching a second
    copy of Anki.
    """
    if _anki_connect_is_available() or _anki_process_is_running():
        return False

    executable = _find_anki_executable()
    if executable is None:
        raise FileNotFoundError(
            "Anki is not running and its executable could not be found. "
            "Set ANKI_PATH or install Anki in its default location."
        )
    try:
        subprocess.Popen(
            [str(executable)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RuntimeError(f"Unable to start Anki at {executable}: {exc}") from exc

    deadline = time.monotonic() + ANKI_STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _anki_connect_is_available():
            return True
        time.sleep(ANKI_STARTUP_POLL_SECONDS)
    raise ConnectionError(
        "Anki was started, but AnkiConnect did not become available within "
        f"{ANKI_STARTUP_TIMEOUT_SECONDS:g} seconds."
    )


def _anki_connect_is_available() -> bool:
    try:
        anki_connect_invoke("version")
    except (ConnectionError, RuntimeError):
        return False
    return True


def _anki_process_is_running() -> bool:
    """Return whether a local Anki desktop process is already running."""
    try:
        import psutil
    except ImportError:  # pragma: no cover - psutil is a declared dependency
        return False
    for process in psutil.process_iter(["name"]):
        try:
            if (process.info["name"] or "").lower() in {"anki", "anki.exe"}:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _find_anki_executable() -> str | None:
    """Find a Windows Anki executable, honoring an explicit ``ANKI_PATH`` first."""
    configured = os.environ.get("ANKI_PATH")
    candidates = [configured] if configured else []
    candidates.extend(
        [
            DEFAULT_ANKI_PATH,
            r"C:\Program Files\Anki\anki.exe",
            r"C:\Program Files (x86)\Anki\anki.exe",
        ]
    )
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return shutil.which("anki") or shutil.which("anki.exe")


def anki_connect_request(action, **params):
    return {"action": action, "version": 6, "params": params}


def anki_connect_invoke(action, **params):
    logger.debug(f"AnkiConnect API call: action={action}, params={params}")
    request_json = json.dumps(anki_connect_request(action, **params)).encode("utf-8")
    try:
        response = json.load(
            urllib.request.urlopen(
                urllib.request.Request(ANKI_CONNECT_URL, request_json)
            )
        )
    except urllib.error.URLError as exc:
        logger.error(f"Failed to connect to AnkiConnect at {ANKI_CONNECT_URL}", exc_info=True)
        raise ConnectionError(
            f"Failed to connect to AnkiConnect at {ANKI_CONNECT_URL}. "
            "Make sure Anki is running and AnkiConnect is installed."
        ) from exc

    if len(response) != 2 or "error" not in response or "result" not in response:
        logger.error(f"Unexpected response from AnkiConnect: {response}")
        raise RuntimeError("Unexpected response from AnkiConnect")
    if response["error"] is not None:
        logger.error(f"AnkiConnect error for action '{action}': {response['error']}")
        raise RuntimeError(f"AnkiConnect error: {response['error']}")
    logger.debug(f"AnkiConnect API call successful: action={action}")
    return response["result"]


def test_anki_connection():
    logger.info("Testing Anki connection")
    try:
        version = anki_connect_invoke("version")
        logger.debug(f"AnkiConnect version: {version}")
    except ConnectionError:
        logger.warning("Anki connection test failed: unable to connect")
        return False

    deck_names = anki_connect_invoke("deckNames")
    model_names = anki_connect_invoke("modelNames")
    deck_exists = DECK_NAME in deck_names
    model_exists = MODEL_NAME in model_names

    if deck_exists and model_exists:
        logger.info(f"Anki connection successful: deck '{DECK_NAME}' and model '{MODEL_NAME}' found")
    else:
        missing = []
        if not deck_exists:
            missing.append(f"deck '{DECK_NAME}'")
        if not model_exists:
            missing.append(f"model '{MODEL_NAME}'")
        logger.warning(f"Anki connection test failed: missing {' and '.join(missing)}")

    return deck_exists and model_exists


def highlight_word_in_sentence(sentence, target_word):
    sentence_escaped = sentence.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    target_word_escaped = target_word.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    pattern = re.escape(target_word_escaped)
    return re.sub(
        f"({pattern})",
        r'<span style="color: red;">[\1]</span>',
        sentence_escaped,
        flags=re.IGNORECASE,
    )


def fetch_deck_words() -> set:
    logger.info(f"Fetching vocabulary from Anki deck '{DECK_NAME}'")
    note_ids = anki_connect_invoke("findNotes", query=f'deck:"{DECK_NAME}"')
    logger.info(f"Found {len(note_ids)} notes in deck")
    if not note_ids:
        logger.info("No notes found in deck, returning empty vocabulary set")
        return set()
    notes = anki_connect_invoke("notesInfo", notes=note_ids)
    logger.debug(f"Retrieved info for {len(notes)} notes")
    words: set[str] = set()
    span_re = re.compile(r'<span[^>]*color:\s*red[^>]*>(.*?)</span>', re.IGNORECASE)
    bracket_re = re.compile(r'\[([^\[\]]+)\]')
    tag_re = re.compile(r'<[^>]+>')
    for note in notes:
        front = note.get("fields", {}).get("Front", {}).get("value", "")
        word = None
        span_match = span_re.search(front)
        if span_match:
            inner = tag_re.sub("", span_match.group(1)).strip()
            bracket_match = bracket_re.search(inner)
            word = bracket_match.group(1).strip().lower() if bracket_match else inner.lower()
        else:
            text = tag_re.sub("", front)
            bracket_match = bracket_re.search(text)
            if bracket_match:
                word = bracket_match.group(1).strip().lower()
        if word:
            words.add(word)
    sample_words = sorted(words)[:10]
    logger.info(f"Extracted {len(words)} unique words from deck")
    logger.debug(f"Sample words: {sample_words}{'...' if len(words) > 10 else ''}")
    return words


def add_anki_card(sentence, target_word, translation):
    logger.info(f"Adding Anki card: word='{target_word}', sentence_length={len(sentence)} chars")
    logger.debug(f"Card details: sentence='{sentence[:100]}...', translation='{translation}'")
    note = {
        "deckName": DECK_NAME,
        "modelName": MODEL_NAME,
        "fields": {
            "Front": highlight_word_in_sentence(sentence, target_word),
            "Back": translation,
        },
        "tags": ["sentence-mining", "auto-generated"],
    }
    try:
        note_id = anki_connect_invoke("addNote", note=note)
        logger.info(f"Card added successfully: word='{target_word}', note_id={note_id}")
        return note_id
    except Exception as e:
        logger.error(f"Failed to add card for word '{target_word}': {e}", exc_info=True)
        raise

