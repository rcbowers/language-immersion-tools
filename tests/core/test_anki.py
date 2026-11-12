"""Tests for the AnkiConnect helpers in core/anki.py (no real Anki, no network)."""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from immersion_app.core import anki


@pytest.fixture(autouse=True)
def _restore_settings():
    original = anki.get_anki_settings()
    yield
    anki.configure_anki(original)


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _respond(payload):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    return _FakeResponse(body)


def _patch_urlopen(monkeypatch, handler):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append({"url": request.full_url, "timeout": timeout, "body": json.loads(request.data)})
        result = handler(request, timeout)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(anki.urllib.request, "urlopen", fake_urlopen)
    return calls


# --- anki_connect_invoke -------------------------------------------------


def test_invoke_returns_result_and_uses_configured_url(monkeypatch):
    anki.configure_anki(anki.AnkiSettings(connect_url="http://example:1234"))
    calls = _patch_urlopen(monkeypatch, lambda r, t: _respond({"result": 6, "error": None}))
    assert anki.anki_connect_invoke("version") == 6
    assert calls[0]["url"] == "http://example:1234"
    assert calls[0]["timeout"] == anki.ANKI_REQUEST_TIMEOUT_SECONDS == 10.0
    assert calls[0]["body"] == {"action": "version", "version": 6, "params": {}}


def test_invoke_explicit_url_and_bulk_timeout(monkeypatch):
    calls = _patch_urlopen(monkeypatch, lambda r, t: _respond({"result": [], "error": None}))
    anki.anki_connect_invoke("findNotes", _timeout=anki.ANKI_BULK_REQUEST_TIMEOUT_SECONDS, _url="http://other", query="x")
    assert calls[0]["url"] == "http://other"
    assert calls[0]["timeout"] == 60.0
    assert calls[0]["body"]["params"] == {"query": "x"}


@pytest.mark.parametrize(
    "exc", [urllib.error.URLError("refused"), TimeoutError("slow"), OSError("boom")]
)
def test_invoke_connection_problems_become_connection_error(monkeypatch, exc):
    _patch_urlopen(monkeypatch, lambda r, t: exc)
    with pytest.raises(ConnectionError, match="AnkiConnect"):
        anki.anki_connect_invoke("version")


def test_invoke_bad_json_is_runtime_error(monkeypatch):
    _patch_urlopen(monkeypatch, lambda r, t: _respond(b"<html>not json"))
    with pytest.raises(RuntimeError, match="invalid JSON"):
        anki.anki_connect_invoke("version")


@pytest.mark.parametrize(
    "payload", [{"result": 1}, {"error": None}, {"result": 1, "error": None, "extra": 1}, {}]
)
def test_invoke_unexpected_shape_is_runtime_error(monkeypatch, payload):
    _patch_urlopen(monkeypatch, lambda r, t: _respond(payload))
    with pytest.raises(RuntimeError, match="Unexpected response"):
        anki.anki_connect_invoke("version")


def test_invoke_anki_error_is_runtime_error(monkeypatch):
    _patch_urlopen(monkeypatch, lambda r, t: _respond({"result": None, "error": "cannot create note because it is a duplicate"}))
    with pytest.raises(RuntimeError, match="AnkiConnect error: cannot create note because it is a duplicate"):
        anki.anki_connect_invoke("addNote")


# --- AnkiSettings --------------------------------------------------------


def test_settings_round_trip():
    settings = anki.AnkiSettings(deck_name="Deck", note_type="Cloze", sentence_field="Text", translation_field="Extra",
                                 connect_url="http://x:1", tags=("a", "b"))
    assert anki.AnkiSettings.from_dict(settings.to_dict()) == settings
    assert settings.to_dict()["tags"] == ["a", "b"]


def test_settings_tags_from_string_and_list():
    assert anki.AnkiSettings.from_dict({"tags": "one, two  three"}).tags == ("one", "two", "three")
    assert anki.AnkiSettings.from_dict({"tags": [" a ", "", "b"]}).tags == ("a", "b")
    assert anki.AnkiSettings.from_dict({"tags": []}).tags == ()


def test_settings_defaults_for_blank_and_bad_input():
    defaults = anki.AnkiSettings()
    assert anki.AnkiSettings.from_dict({"deck_name": "   ", "note_type": None}) == defaults
    assert anki.AnkiSettings.from_dict(None) == defaults
    assert anki.AnkiSettings.from_dict("not a dict") == defaults
    assert anki.AnkiSettings.from_dict({"tags": 5}).tags == anki.DEFAULT_TAGS


def test_settings_with_changes_does_not_mutate():
    base = anki.AnkiSettings()
    changed = base.with_changes(deck_name="Other")
    assert changed.deck_name == "Other"
    assert base.deck_name == anki.DEFAULT_DECK_NAME


# --- check_anki_setup ----------------------------------------------------


def _fake_invoke(monkeypatch, responses):
    """responses: action -> value, or an Exception to raise."""
    seen = []

    def fake(action, _timeout=None, _url=None, **params):
        seen.append((action, params))
        value = responses[action]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(anki, "anki_connect_invoke", fake)
    return seen


def _settings():
    return anki.AnkiSettings(deck_name="D", note_type="N", sentence_field="Front", translation_field="Back")


def test_setup_ok(monkeypatch):
    _fake_invoke(monkeypatch, {"version": 6, "deckNames": ["D"], "modelNames": ["N"], "modelFieldNames": ["Front", "Back"]})
    status = anki.check_anki_setup(_settings())
    assert status.ok and status.message == "Ready"


def test_setup_missing_deck_note_type_and_fields(monkeypatch):
    _fake_invoke(monkeypatch, {"version": 6, "deckNames": [], "modelNames": [], "modelFieldNames": []})
    status = anki.check_anki_setup(_settings())
    assert status.connected and not status.ok
    assert "deck 'D' not found" in status.message
    assert "note type 'N' not found" in status.message


def test_setup_missing_fields_message(monkeypatch):
    _fake_invoke(monkeypatch, {"version": 6, "deckNames": ["D"], "modelNames": ["N"], "modelFieldNames": ["Front"]})
    status = anki.check_anki_setup(_settings())
    assert status.missing_fields == ("Back",)
    assert "has no field(s) Back" in status.message
    assert not status.ok


def test_setup_connection_failure_does_not_raise(monkeypatch):
    _fake_invoke(monkeypatch, {"version": ConnectionError("Anki is closed")})
    status = anki.check_anki_setup(_settings())
    assert status.connected is False
    assert "Anki is closed" in status.message


def test_setup_model_field_lookup_failure_does_not_crash(monkeypatch):
    _fake_invoke(monkeypatch, {"version": 6, "deckNames": ["D"], "modelNames": ["N"], "modelFieldNames": RuntimeError("gone")})
    status = anki.check_anki_setup(_settings())
    assert status.connected
    assert set(status.missing_fields) == {"Front", "Back"}


def test_connection_test_wrapper(monkeypatch):
    _fake_invoke(monkeypatch, {"version": 6, "deckNames": ["Language Immersion Tools"], "modelNames": ["Basic"], "modelFieldNames": ["Front", "Back"]})
    assert anki.test_anki_connection() is True
    _fake_invoke(monkeypatch, {"version": ConnectionError("x")})
    assert anki.test_anki_connection() is False


# --- highlight_word_in_sentence / add_anki_card --------------------------


def test_highlight_wraps_word_in_red_span():
    assert anki.highlight_word_in_sentence("El gato duerme", "gato") == 'El <span style="color: red;">[gato]</span> duerme'


def test_highlight_is_case_insensitive_and_keeps_original_case():
    assert '[Gato]' in anki.highlight_word_in_sentence("Gato grande", "gato")


def test_highlight_escapes_html():
    result = anki.highlight_word_in_sentence("<b>a & b</b> gato", "gato")
    assert "<b>" not in result
    assert "&lt;b&gt;a &amp; b&lt;/b&gt;" in result


@pytest.mark.parametrize("word", ["a.b", "(x)", "c++", "[y]", "a|b", "$"])
def test_highlight_regex_characters_in_word_are_literal(word):
    sentence = f"before {word} after axb"
    result = anki.highlight_word_in_sentence(sentence, word)
    assert result.count('color: red') == 1
    assert "axb" in result  # the '.' in "a.b" must not match "axb"


def test_highlight_word_with_html_chars():
    result = anki.highlight_word_in_sentence("AT&T rocks", "AT&T")
    assert '[AT&amp;T]' in result


def test_add_card_builds_note_from_settings(monkeypatch):
    anki.configure_anki(anki.AnkiSettings(deck_name="MyDeck", note_type="Cloze", sentence_field="Text",
                                          translation_field="Extra", tags=("t1", "t2")))
    seen = _fake_invoke(monkeypatch, {"addNote": 42})
    assert anki.add_anki_card("El gato duerme", "gato", "cat") == 42
    action, params = seen[0]
    assert action == "addNote"
    note = params["note"]
    assert note["deckName"] == "MyDeck"
    assert note["modelName"] == "Cloze"
    assert note["tags"] == ["t1", "t2"]
    assert note["fields"]["Text"] == 'El <span style="color: red;">[gato]</span> duerme'
    assert note["fields"]["Extra"] == "cat"


def test_add_card_propagates_errors(monkeypatch):
    _fake_invoke(monkeypatch, {"addNote": RuntimeError("AnkiConnect error: duplicate")})
    with pytest.raises(RuntimeError, match="duplicate"):
        anki.add_anki_card("s", "w", "t")


# --- fetch_deck_words ----------------------------------------------------


def _note(value, field="Front"):
    return {"fields": {field: {"value": value}}}


def test_fetch_words_parses_red_span_bracket_and_bare_forms(monkeypatch):
    notes = [
        _note('El <span style="color: red;">[Gato]</span> duerme'),
        _note('<span style="color:red">perro</span> corre'),
        _note("Ella tiene un [Libro] nuevo"),
        _note('<span style="color: red;"><b>[nested]</b></span>'),
        _note("No marker here"),
        _note(""),
    ]
    seen = _fake_invoke(monkeypatch, {"findNotes": [1, 2, 3, 4, 5, 6], "notesInfo": notes})
    assert anki.fetch_deck_words() == {"gato", "perro", "libro", "nested"}
    assert seen[0][1]["query"] == 'deck:"Language Immersion Tools"'


def test_fetch_words_empty_deck_skips_notes_info(monkeypatch):
    seen = _fake_invoke(monkeypatch, {"findNotes": []})
    assert anki.fetch_deck_words() == set()
    assert [action for action, _ in seen] == ["findNotes"]


def test_fetch_words_honors_custom_sentence_field_and_deck(monkeypatch):
    anki.configure_anki(anki.AnkiSettings(deck_name="Mine", sentence_field="Text"))
    seen = _fake_invoke(monkeypatch, {"findNotes": [1], "notesInfo": [_note("hola [Mundo]", field="Text")]})
    assert anki.fetch_deck_words() == {"mundo"}
    assert seen[0][1]["query"] == 'deck:"Mine"'


def test_fetch_words_ignores_notes_missing_the_field(monkeypatch):
    _fake_invoke(monkeypatch, {"findNotes": [1], "notesInfo": [_note("hola [Mundo]", field="Other")]})
    assert anki.fetch_deck_words() == set()


# --- list helpers / load_anki_options ------------------------------------


def test_list_helpers_sort_and_pass_url(monkeypatch):
    seen = _fake_invoke(monkeypatch, {"deckNames": ["b", "a"], "modelNames": ["z", "y"], "modelFieldNames": ["F", "B"], "createDeck": 7})
    assert anki.list_decks() == ["a", "b"]
    assert anki.list_note_types() == ["y", "z"]
    assert anki.list_note_fields("Basic") == ["F", "B"]
    assert anki.create_deck("New") == 7
    assert seen[2][1] == {"modelName": "Basic"}
    assert seen[3][1] == {"deck": "New"}


def test_load_options_failing_note_type_yields_empty_fields(monkeypatch):
    def fake(action, _timeout=None, _url=None, **params):
        if action == "deckNames":
            return ["D"]
        if action == "modelNames":
            return ["Good", "Bad"]
        if action == "modelFieldNames":
            if params["modelName"] == "Bad":
                raise RuntimeError("model not found")
            return ["Front", "Back"]
        raise AssertionError(action)

    monkeypatch.setattr(anki, "anki_connect_invoke", fake)
    decks, fields = anki.load_anki_options()
    assert decks == ["D"]
    assert fields == {"Good": ["Front", "Back"], "Bad": []}


# --- executable lookup / startup errors ----------------------------------


def test_find_executable_prefers_ankipath_env(monkeypatch, tmp_path):
    custom = tmp_path / "myanki.exe"
    custom.write_text("x")
    monkeypatch.setenv("ANKI_PATH", str(custom))
    monkeypatch.setattr(anki, "_default_anki_paths", lambda: [str(tmp_path / "default.exe")])
    (tmp_path / "default.exe").write_text("x")
    assert anki.find_anki_executable() == str(custom)


def test_find_executable_falls_back_to_defaults_then_path(monkeypatch, tmp_path):
    default = tmp_path / "default.exe"
    monkeypatch.setenv("ANKI_PATH", str(tmp_path / "missing.exe"))
    monkeypatch.setattr(anki, "_default_anki_paths", lambda: [str(default)])
    monkeypatch.setattr(anki.shutil, "which", lambda name: None)
    assert anki.find_anki_executable() is None
    default.write_text("x")
    assert anki.find_anki_executable() == str(default)
    default.unlink()
    monkeypatch.setattr(anki.shutil, "which", lambda name: "/usr/bin/anki" if name == "anki" else None)
    assert anki.find_anki_executable() == "/usr/bin/anki"


def _no_anki_running(monkeypatch):
    monkeypatch.setattr(anki, "_anki_connect_is_available", lambda: False)
    monkeypatch.setattr(anki, "_anki_process_is_running", lambda: False)


def test_start_without_executable_raises_file_not_found(monkeypatch):
    _no_anki_running(monkeypatch)
    monkeypatch.setattr(anki, "_find_anki_executable", lambda: None)
    with pytest.raises(FileNotFoundError, match="ANKI_PATH"):
        anki.start_anki_if_needed()


def test_start_popen_failure_is_runtime_error(monkeypatch):
    _no_anki_running(monkeypatch)
    monkeypatch.setattr(anki, "_find_anki_executable", lambda: "anki.exe")

    def boom(*a, **k):
        raise OSError("denied")

    monkeypatch.setattr(anki.subprocess, "Popen", boom)
    with pytest.raises(RuntimeError, match="Unable to start Anki"):
        anki.start_anki_if_needed()


def test_start_that_never_becomes_available_is_connection_error(monkeypatch):
    _no_anki_running(monkeypatch)
    monkeypatch.setattr(anki, "_find_anki_executable", lambda: "anki.exe")
    monkeypatch.setattr(anki.subprocess, "Popen", lambda *a, **k: object())
    clock = {"now": 0.0}
    monkeypatch.setattr(anki.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(anki.time, "sleep", lambda s: clock.__setitem__("now", clock["now"] + s))
    with pytest.raises(ConnectionError, match="did not become available"):
        anki.start_anki_if_needed()
    assert clock["now"] >= anki.ANKI_STARTUP_TIMEOUT_SECONDS


def test_connect_is_available_swallows_errors(monkeypatch):
    def fake(action, **kw):
        raise ConnectionError("x")

    monkeypatch.setattr(anki, "anki_connect_invoke", fake)
    assert anki._anki_connect_is_available() is False
    monkeypatch.setattr(anki, "anki_connect_invoke", lambda action, **kw: 6)
    assert anki._anki_connect_is_available() is True
