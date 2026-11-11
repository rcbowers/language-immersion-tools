"""Tests for the persisted card queue (user data: must never be lost)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from immersion_app.core import queue_store


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point every queue_store path at a throwaway folder."""
    queue_dir = tmp_path / "queue"
    log_dir = tmp_path / "logs"
    paths = {
        "QUEUE_JSON_PATH": queue_dir / "queued_cards.json",
        "PROCESSED_LOG_PATH": log_dir / "processed_cards.log",
        "LEGACY_QUEUE_PATH": tmp_path / "words_to_process.txt",
        "LEGACY_PROCESSED_PATH": tmp_path / "processed_words.txt",
    }
    for name, value in paths.items():
        monkeypatch.setattr(queue_store, name, value)

    def ensure():
        queue_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(queue_store, "ensure_runtime_dirs", ensure)
    return type("Store", (), paths)


def _entry(word="gato", sentence="El gato duerme.", translation="cat", **extra):
    entry = {"word": word, "sentence": sentence, "translation": translation}
    entry.update(extra)
    return entry


def test_round_trip_preserves_non_ascii(store):
    entries = [
        _entry("猫", "猫が好きです。", "cat"),
        _entry("niño", "El niño está aquí.", "boy"),
    ]
    queue_store.save_queue_entries(entries)
    assert queue_store.load_queue_entries() == entries
    # Stored as readable UTF-8, not \u escapes.
    assert "猫" in store.QUEUE_JSON_PATH.read_text(encoding="utf-8")


def test_empty_when_nothing_saved(store):
    assert queue_store.load_queue_entries() == []
    assert queue_store.queue_count() == 0


def test_save_leaves_no_tmp_file(store):
    queue_store.save_queue_entries([_entry()])
    assert not store.QUEUE_JSON_PATH.with_suffix(".tmp").exists()
    assert store.QUEUE_JSON_PATH.exists()


def test_failed_write_keeps_previous_queue(store, monkeypatch):
    original = [_entry("uno")]
    queue_store.save_queue_entries(original)

    real_write_text = Path.write_text

    def boom(self, *args, **kwargs):
        if self.suffix == ".tmp":
            raise OSError("disk full")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", boom)
    with pytest.raises(OSError):
        queue_store.save_queue_entries([_entry("dos")])
    monkeypatch.setattr(Path, "write_text", real_write_text)

    assert json.loads(store.QUEUE_JSON_PATH.read_text(encoding="utf-8")) == original


def test_corrupt_json_falls_back_to_legacy(store):
    store.QUEUE_JSON_PATH.parent.mkdir(parents=True)
    store.QUEUE_JSON_PATH.write_text("{not json", encoding="utf-8")
    store.LEGACY_QUEUE_PATH.write_text("sentence\nword\ntrans\n", encoding="utf-8")

    entries = queue_store.load_queue_entries()
    assert [e["word"] for e in entries] == ["word"]


def test_corrupt_json_without_legacy_is_empty(store):
    store.QUEUE_JSON_PATH.parent.mkdir(parents=True)
    store.QUEUE_JSON_PATH.write_text("{not json", encoding="utf-8")
    assert queue_store.load_queue_entries() == []


def test_json_dict_instead_of_list_falls_back_to_legacy(store):
    store.QUEUE_JSON_PATH.parent.mkdir(parents=True)
    store.QUEUE_JSON_PATH.write_text('{"word": "x"}', encoding="utf-8")
    store.LEGACY_QUEUE_PATH.write_text("s\nw\nt\n", encoding="utf-8")
    assert [e["word"] for e in queue_store.load_queue_entries()] == ["w"]


def test_non_dict_entries_are_dropped(store):
    store.QUEUE_JSON_PATH.parent.mkdir(parents=True)
    store.QUEUE_JSON_PATH.write_text(json.dumps([_entry("ok"), "junk", 3, None]), encoding="utf-8")
    assert [e["word"] for e in queue_store.load_queue_entries()] == ["ok"]


def test_legacy_three_line_format(store):
    store.LEGACY_QUEUE_PATH.write_text(
        "Sentence one.\nuno\none\n\n\nSentence two.\ndos\ntwo\nPartial sentence\npartial\n",
        encoding="utf-8",
    )
    entries = queue_store.load_queue_entries()

    assert [(e["sentence"], e["word"], e["translation"]) for e in entries] == [
        ("Sentence one.", "uno", "one"),
        ("Sentence two.", "dos", "two"),
    ]  # trailing partial group is ignored
    assert all(e["source_name"] == "legacy-import" for e in entries)
    assert all(e["status"] == "queued" for e in entries)


def test_legacy_empty_file_is_empty(store):
    store.LEGACY_QUEUE_PATH.write_text("  \n\n", encoding="utf-8")
    assert queue_store.load_queue_entries() == []


def test_append_and_count(store):
    queue_store.append_queue_entry(_entry("uno"))
    queue_store.append_queue_entry(_entry("dos"))
    assert queue_store.queue_count() == 2
    assert [e["word"] for e in queue_store.load_queue_entries()] == ["uno", "dos"]


def test_processed_log_written(store):
    queue_store.append_processed_log([_entry("gato", source_name="book.pdf", location="Page 3")])
    text = store.PROCESSED_LOG_PATH.read_text(encoding="utf-8")
    assert "gato - cat | book.pdf | Page 3" in text
    assert "Sentence: El gato duerme." in text
    assert not store.LEGACY_PROCESSED_PATH.exists()


def test_processed_log_appends_not_overwrites(store):
    queue_store.append_processed_log([_entry("uno")])
    queue_store.append_processed_log([_entry("dos")])
    text = store.PROCESSED_LOG_PATH.read_text(encoding="utf-8")
    assert "uno" in text and "dos" in text


def test_legacy_processed_log_only_written_if_it_exists(store):
    store.LEGACY_PROCESSED_PATH.write_text("old\n", encoding="utf-8")
    queue_store.append_processed_log([_entry("gato")])
    legacy = store.LEGACY_PROCESSED_PATH.read_text(encoding="utf-8")
    assert legacy.startswith("old\n")
    assert "gato - cat" in legacy
