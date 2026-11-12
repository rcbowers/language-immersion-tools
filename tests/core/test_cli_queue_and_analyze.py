"""CLI tools: the queue processor (fake Anki) and the pure text helpers of the analyzer."""

from __future__ import annotations

import pytest

from immersion_app.cli import analyze
from immersion_app.cli import queue as queue_cli


# --- cli/queue.py --------------------------------------------------------


@pytest.fixture
def cli(monkeypatch):
    state = {"queue": [], "log": [], "added": [], "connected": True, "fail_words": set()}
    monkeypatch.setattr(queue_cli, "setup_cli_logging", lambda: None)
    monkeypatch.setattr(queue_cli, "load_user_data", lambda: {"anki": {"deck_name": "CliDeck"}})
    monkeypatch.setattr(queue_cli, "test_anki_connection", lambda: state["connected"])
    monkeypatch.setattr(queue_cli, "load_queue_entries", lambda: list(state["queue"]))
    monkeypatch.setattr(queue_cli, "save_queue_entries", lambda entries: state.__setitem__("queue", list(entries)))
    monkeypatch.setattr(queue_cli, "append_processed_log", lambda entries: state["log"].extend(entries))

    def add(sentence, word, translation):
        if word in state["fail_words"]:
            raise RuntimeError("AnkiConnect error: duplicate")
        state["added"].append((sentence, word, translation))

    monkeypatch.setattr(queue_cli, "add_anki_card", add)
    original = queue_cli.get_anki_settings()
    yield state
    queue_cli.configure_anki(original)


def _entry(word, sentence="Frase."):
    return {"word": word, "sentence": sentence, "translation": f"{word}-en"}


def test_queue_cli_adds_all_and_empties_queue(cli):
    cli["queue"] = [_entry("a"), _entry("b")]
    assert queue_cli.main() == 0
    assert [c[1] for c in cli["added"]] == ["a", "b"]
    assert cli["queue"] == [] and [e["word"] for e in cli["log"]] == ["a", "b"]


def test_queue_cli_uses_deck_from_app_settings(cli):
    cli["connected"] = False
    queue_cli.main()
    assert queue_cli.get_anki_settings().deck_name == "CliDeck"


def test_queue_cli_returns_1_and_keeps_queue_when_anki_unavailable(cli):
    cli["connected"] = False
    cli["queue"] = [_entry("a")]
    assert queue_cli.main() == 1
    assert cli["added"] == [] and [e["word"] for e in cli["queue"]] == ["a"]


def test_queue_cli_empty_queue_is_success(cli):
    assert queue_cli.main() == 0
    assert cli["added"] == []


def test_queue_cli_keeps_only_failures_and_returns_1(cli):
    cli["fail_words"] = {"b"}
    cli["queue"] = [_entry("a"), _entry("b"), _entry("c")]
    assert queue_cli.main() == 1
    assert [e["word"] for e in cli["queue"]] == ["b"]
    assert [e["word"] for e in cli["log"]] == ["a", "c"]


def test_queue_cli_numbers_duplicate_sentences(cli):
    cli["queue"] = [_entry("a", "Same."), _entry("b", "Same."), _entry("c", "Same.")]
    queue_cli.main()
    assert [c[0] for c in cli["added"]] == ["Same.", "Same. (2)", "Same. (3)"]


def test_queue_cli_does_not_write_log_when_everything_fails(cli):
    cli["fail_words"] = {"a"}
    cli["queue"] = [_entry("a")]
    assert queue_cli.main() == 1
    assert cli["log"] == []


# --- cli/analyze.py pure helpers -----------------------------------------


@pytest.mark.parametrize(
    "line, expected",
    [("", True), ("   ", True), ("42", True), ("00:00:01,000 --> 00:00:02,000", True), ("Hola mundo", False)],
)
def test_srt_metadata_lines(line, expected):
    assert analyze.is_srt_metadata_line(line) is expected


def test_clean_spanish_text_lowercases_and_strips_punctuation():
    assert analyze.clean_spanish_text("¿Qué PASÓ, niño?! 123 ...") == "qué pasó niño"
    assert analyze.clean_spanish_text("Pingüino   y\tcigüeña") == "pingüino y cigüeña"
    assert analyze.clean_spanish_text("") == ""


def test_normalize_accents():
    assert analyze.normalize_accents("canción niño pingüino") == "cancion nino pinguino"
    assert analyze.normalize_accents("plain") == "plain"


def test_filter_stopwords():
    words = ["el", "gato", "y", "el", "perro"]
    filtered, removed = analyze.filter_stopwords(words)
    assert filtered == ["gato", "perro"] and removed == 3
    assert analyze.filter_stopwords(words, remove_stopwords=False) == (words, 0)


def test_parse_srt_file_skips_numbers_and_timestamps(tmp_path):
    path = tmp_path / "ep.srt"
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\n¡Hola, mundo!\n\n2\n00:00:03,000 --> 00:00:04,000\nAdiós amigo\n", encoding="utf-8")
    assert analyze.parse_srt_file(str(path)) == ["hola", "mundo", "adiós", "amigo"]


def test_parse_txt_file_and_document_dispatch(tmp_path):
    txt = tmp_path / "a.txt"
    txt.write_text("El Gato, duerme.\nOtra línea", encoding="utf-8")
    assert analyze.parse_document(str(txt)) == ["el", "gato", "duerme", "otra", "línea"]
    other = tmp_path / "a.docx"
    other.write_text("x", encoding="utf-8")
    assert analyze.parse_document(str(other)) == []


def test_parse_pdf_requires_pypdf(monkeypatch, tmp_path):
    monkeypatch.setattr(analyze, "PDF_AVAILABLE", False)
    with pytest.raises(ImportError, match="pypdf"):
        analyze.parse_pdf_file(str(tmp_path / "x.pdf"))
