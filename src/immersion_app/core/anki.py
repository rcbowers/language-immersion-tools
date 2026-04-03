"""AnkiConnect helpers for the immersion app."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


DECK_NAME = "2025 Spanish Immersion"
MODEL_NAME = "Basic"
ANKI_CONNECT_URL = "http://localhost:8765"


def anki_connect_request(action, **params):
    return {"action": action, "version": 6, "params": params}


def anki_connect_invoke(action, **params):
    request_json = json.dumps(anki_connect_request(action, **params)).encode("utf-8")
    try:
        response = json.load(
            urllib.request.urlopen(
                urllib.request.Request(ANKI_CONNECT_URL, request_json)
            )
        )
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Failed to connect to AnkiConnect at {ANKI_CONNECT_URL}. "
            "Make sure Anki is running and AnkiConnect is installed."
        ) from exc

    if len(response) != 2 or "error" not in response or "result" not in response:
        raise RuntimeError("Unexpected response from AnkiConnect")
    if response["error"] is not None:
        raise RuntimeError(f"AnkiConnect error: {response['error']}")
    return response["result"]


def test_anki_connection():
    try:
        anki_connect_invoke("version")
    except ConnectionError:
        return False

    deck_names = anki_connect_invoke("deckNames")
    model_names = anki_connect_invoke("modelNames")
    return DECK_NAME in deck_names and MODEL_NAME in model_names


def highlight_word_in_sentence(sentence, target_word):
    sentence_escaped = sentence.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    target_word_escaped = target_word.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    pattern = re.escape(target_word_escaped)
    return re.sub(
        f"({pattern})",
        r'<span style="color: red;">\1</span>',
        sentence_escaped,
        flags=re.IGNORECASE,
    )


def add_anki_card(sentence, target_word, translation):
    note = {
        "deckName": DECK_NAME,
        "modelName": MODEL_NAME,
        "fields": {
            "Front": highlight_word_in_sentence(sentence, target_word),
            "Back": translation,
        },
        "tags": ["sentence-mining", "auto-generated"],
    }
    return anki_connect_invoke("addNote", note=note)

