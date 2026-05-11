"""AnkiConnect helpers for the immersion app."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


DECK_NAME = "2025 Spanish Immersion"
MODEL_NAME = "Basic"
ANKI_CONNECT_URL = "http://localhost:8765"


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

