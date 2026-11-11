"""Tests for the persisted Anki vocabulary snapshot."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from immersion_app.core import anki_snapshot


@pytest.fixture
def snap_path(tmp_path, monkeypatch):
    path = tmp_path / "state" / "anki_snapshot.json"
    monkeypatch.setattr(anki_snapshot, "ANKI_SNAPSHOT_PATH", path)
    monkeypatch.setattr(
        anki_snapshot, "get_anki_settings", lambda: SimpleNamespace(deck_name="Spanish")
    )
    return path


def test_round_trip(snap_path):
    anki_snapshot.save_snapshot({"niño", "猫", "gato"})
    assert anki_snapshot.load_snapshot() == {"niño", "猫", "gato"}


def test_saved_file_is_sorted_and_tagged_with_deck(snap_path):
    anki_snapshot.save_snapshot({"b", "a"})
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    assert data["words"] == ["a", "b"]
    assert data["deck"] == "Spanish"
    assert data["updated_at"]


def test_missing_file_is_empty(snap_path):
    assert anki_snapshot.load_snapshot() == set()


def test_corrupt_file_is_empty(snap_path):
    snap_path.parent.mkdir(parents=True)
    snap_path.write_text("{oops", encoding="utf-8")
    assert anki_snapshot.load_snapshot() == set()


def test_snapshot_from_different_deck_is_ignored(snap_path, monkeypatch):
    anki_snapshot.save_snapshot({"gato"})
    monkeypatch.setattr(
        anki_snapshot, "get_anki_settings", lambda: SimpleNamespace(deck_name="French")
    )
    assert anki_snapshot.load_snapshot() == set()


def test_snapshot_without_deck_is_accepted(snap_path):
    snap_path.parent.mkdir(parents=True)
    snap_path.write_text(json.dumps({"words": ["viejo"]}), encoding="utf-8")
    assert anki_snapshot.load_snapshot() == {"viejo"}
