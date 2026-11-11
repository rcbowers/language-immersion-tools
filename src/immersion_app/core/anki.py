"""AnkiConnect helpers for the immersion app."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field, replace

logger = logging.getLogger(__name__)


DEFAULT_DECK_NAME = "LinguaLoop"
DEFAULT_NOTE_TYPE = "Basic"
DEFAULT_SENTENCE_FIELD = "Front"
DEFAULT_TRANSLATION_FIELD = "Back"
DEFAULT_ANKI_CONNECT_URL = "http://localhost:8765"
DEFAULT_TAGS = ("sentence-mining", "lingualoop")
ANKICONNECT_ADDON_CODE = "2055492159"

ANKI_REQUEST_TIMEOUT_SECONDS = 10.0
ANKI_BULK_REQUEST_TIMEOUT_SECONDS = 60.0
ANKI_STARTUP_TIMEOUT_SECONDS = 20.0
ANKI_STARTUP_POLL_SECONDS = 0.5


@dataclass(frozen=True)
class AnkiSettings:
    """Where and how LinguaLoop creates Anki notes (user-configurable)."""

    deck_name: str = DEFAULT_DECK_NAME
    note_type: str = DEFAULT_NOTE_TYPE
    sentence_field: str = DEFAULT_SENTENCE_FIELD
    translation_field: str = DEFAULT_TRANSLATION_FIELD
    connect_url: str = DEFAULT_ANKI_CONNECT_URL
    tags: tuple[str, ...] = field(default=DEFAULT_TAGS)

    @classmethod
    def from_dict(cls, data: dict | None) -> "AnkiSettings":
        data = data if isinstance(data, dict) else {}

        def _text(key: str, default: str) -> str:
            value = str(data.get(key) or "").strip()
            return value or default

        raw_tags = data.get("tags")
        if isinstance(raw_tags, str):
            raw_tags = raw_tags.replace(",", " ").split()
        if isinstance(raw_tags, (list, tuple)):
            tags = tuple(str(tag).strip() for tag in raw_tags if str(tag).strip())
        else:
            tags = DEFAULT_TAGS
        return cls(
            deck_name=_text("deck_name", DEFAULT_DECK_NAME),
            note_type=_text("note_type", DEFAULT_NOTE_TYPE),
            sentence_field=_text("sentence_field", DEFAULT_SENTENCE_FIELD),
            translation_field=_text("translation_field", DEFAULT_TRANSLATION_FIELD),
            connect_url=_text("connect_url", DEFAULT_ANKI_CONNECT_URL),
            tags=tags,
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["tags"] = list(self.tags)
        return data

    def with_changes(self, **changes) -> "AnkiSettings":
        return replace(self, **changes)


_settings = AnkiSettings()


def configure_anki(settings: AnkiSettings) -> None:
    """Set the Anki settings used by all module functions (call on startup and when settings change)."""
    global _settings
    _settings = settings
    logger.info(
        "Anki configured: deck=%r note_type=%r fields=(%r, %r) url=%s",
        settings.deck_name, settings.note_type, settings.sentence_field, settings.translation_field, settings.connect_url,
    )


def get_anki_settings() -> AnkiSettings:
    return _settings


def _default_anki_paths() -> list[str]:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = []
    if local_app_data:
        candidates.append(os.path.join(local_app_data, "Programs", "Anki", "anki.exe"))
    candidates.extend(
        [
            r"C:\Program Files\Anki\anki.exe",
            r"C:\Program Files (x86)\Anki\anki.exe",
            "/Applications/Anki.app/Contents/MacOS/anki",
        ]
    )
    return candidates


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
            "Set the ANKI_PATH environment variable or install Anki in its default location."
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


def find_anki_executable() -> str | None:
    """Locate the Anki desktop executable (``ANKI_PATH`` env var first, then default install paths)."""
    return _find_anki_executable()


def _find_anki_executable() -> str | None:
    """Find a Windows Anki executable, honoring an explicit ``ANKI_PATH`` first."""
    configured = os.environ.get("ANKI_PATH")
    candidates = [configured] if configured else []
    candidates.extend(_default_anki_paths())
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return shutil.which("anki") or shutil.which("anki.exe")


def anki_connect_request(action, **params):
    return {"action": action, "version": 6, "params": params}


def anki_connect_invoke(action, _timeout: float = ANKI_REQUEST_TIMEOUT_SECONDS, _url: str | None = None, **params):
    url = _url or _settings.connect_url
    logger.debug(f"AnkiConnect API call: action={action}, params={params}")
    request_json = json.dumps(anki_connect_request(action, **params)).encode("utf-8")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, request_json), timeout=_timeout) as handle:
            response = json.load(handle)
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        logger.warning(f"Failed to reach AnkiConnect at {url}: {exc}")
        raise ConnectionError(
            f"Failed to connect to AnkiConnect at {url}. "
            f"Make sure Anki is running and AnkiConnect (add-on {ANKICONNECT_ADDON_CODE}) is installed."
        ) from exc
    except ValueError as exc:
        raise RuntimeError(f"AnkiConnect at {url} returned invalid JSON") from exc

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

    status = check_anki_setup()
    if status.ok:
        logger.info(f"Anki connection successful: deck '{_settings.deck_name}' and note type '{_settings.note_type}' found")
    else:
        logger.warning(f"Anki connection test failed: {status.message}")
    return status.ok


@dataclass(frozen=True)
class AnkiSetupStatus:
    connected: bool
    deck_exists: bool = False
    note_type_exists: bool = False
    missing_fields: tuple[str, ...] = ()
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.connected and self.deck_exists and self.note_type_exists and not self.missing_fields


def check_anki_setup(settings: AnkiSettings | None = None) -> AnkiSetupStatus:
    """Check AnkiConnect, the configured deck, note type and fields. Never raises for connection errors."""
    settings = settings or _settings
    try:
        anki_connect_invoke("version", _url=settings.connect_url)
        deck_names = anki_connect_invoke("deckNames", _url=settings.connect_url)
        model_names = anki_connect_invoke("modelNames", _url=settings.connect_url)
    except (ConnectionError, RuntimeError) as exc:
        return AnkiSetupStatus(connected=False, message=str(exc))
    deck_exists = settings.deck_name in deck_names
    note_type_exists = settings.note_type in model_names
    missing_fields: tuple[str, ...] = ()
    if note_type_exists:
        try:
            fields = anki_connect_invoke("modelFieldNames", _url=settings.connect_url, modelName=settings.note_type)
        except (ConnectionError, RuntimeError):
            fields = []
        missing_fields = tuple(f for f in (settings.sentence_field, settings.translation_field) if f not in fields)
    problems = []
    if not deck_exists:
        problems.append(f"deck '{settings.deck_name}' not found")
    if not note_type_exists:
        problems.append(f"note type '{settings.note_type}' not found")
    if missing_fields:
        problems.append(f"note type '{settings.note_type}' has no field(s) {', '.join(missing_fields)}")
    return AnkiSetupStatus(
        connected=True,
        deck_exists=deck_exists,
        note_type_exists=note_type_exists,
        missing_fields=missing_fields,
        message="; ".join(problems) if problems else "Ready",
    )


def list_decks(connect_url: str | None = None) -> list[str]:
    return sorted(anki_connect_invoke("deckNames", _url=connect_url))


def list_note_types(connect_url: str | None = None) -> list[str]:
    return sorted(anki_connect_invoke("modelNames", _url=connect_url))


def list_note_fields(note_type: str, connect_url: str | None = None) -> list[str]:
    return list(anki_connect_invoke("modelFieldNames", _url=connect_url, modelName=note_type))


def create_deck(deck_name: str, connect_url: str | None = None):
    return anki_connect_invoke("createDeck", _url=connect_url, deck=deck_name)


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
    settings = _settings
    logger.info(f"Fetching vocabulary from Anki deck '{settings.deck_name}'")
    note_ids = anki_connect_invoke(
        "findNotes", _timeout=ANKI_BULK_REQUEST_TIMEOUT_SECONDS, query=f'deck:"{settings.deck_name}"'
    )
    logger.info(f"Found {len(note_ids)} notes in deck")
    if not note_ids:
        logger.info("No notes found in deck, returning empty vocabulary set")
        return set()
    notes = anki_connect_invoke("notesInfo", _timeout=ANKI_BULK_REQUEST_TIMEOUT_SECONDS, notes=note_ids)
    logger.debug(f"Retrieved info for {len(notes)} notes")
    words: set[str] = set()
    span_re = re.compile(r'<span[^>]*color:\s*red[^>]*>(.*?)</span>', re.IGNORECASE)
    bracket_re = re.compile(r'\[([^\[\]]+)\]')
    tag_re = re.compile(r'<[^>]+>')
    for note in notes:
        front = note.get("fields", {}).get(settings.sentence_field, {}).get("value", "")
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
    settings = _settings
    note = {
        "deckName": settings.deck_name,
        "modelName": settings.note_type,
        "fields": {
            settings.sentence_field: highlight_word_in_sentence(sentence, target_word),
            settings.translation_field: translation,
        },
        "tags": list(settings.tags),
    }
    try:
        note_id = anki_connect_invoke("addNote", note=note)
        logger.info(f"Card added successfully: word='{target_word}', note_id={note_id}")
        return note_id
    except Exception as e:
        logger.error(f"Failed to add card for word '{target_word}': {e}", exc_info=True)
        raise



def load_anki_options(connect_url: str | None = None) -> tuple[list[str], dict[str, list[str]]]:
    """Return (deck names, {note type: field names}) from AnkiConnect. Blocking; call off the UI thread."""
    decks = list_decks(connect_url)
    fields_by_note_type = {}
    for note_type in list_note_types(connect_url):
        try:
            fields_by_note_type[note_type] = list_note_fields(note_type, connect_url)
        except (ConnectionError, RuntimeError):
            fields_by_note_type[note_type] = []
    return decks, fields_by_note_type
