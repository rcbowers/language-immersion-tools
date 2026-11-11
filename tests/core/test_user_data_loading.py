"""Tests for load_user_data resilience (a bad state file must never crash startup)."""

from __future__ import annotations

import json

import pytest

from immersion_app.core import user_data


@pytest.fixture
def state(tmp_path, monkeypatch):
    primary = tmp_path / "state" / "user.json"
    legacy = tmp_path / "legacy_user.json"
    monkeypatch.setattr(user_data, "USER_STATE_PATH", primary)
    monkeypatch.setattr(user_data, "LEGACY_USER_STATE_PATH", legacy)
    monkeypatch.setattr(user_data, "ensure_runtime_dirs", lambda: primary.parent.mkdir(parents=True, exist_ok=True))
    primary.parent.mkdir(parents=True)
    return type("S", (), {"primary": primary, "legacy": legacy})


def test_no_files_gives_defaults(state):
    assert user_data.load_user_data() == user_data.load_user_data()
    data = user_data.load_user_data()
    assert data["preferences"]["learning_language"] == "es"
    assert data["recent_files"] == [] and data["progress"] == {"completed_pages": {}, "completed_videos": {}}


def test_corrupt_primary_file_does_not_crash_and_gives_defaults(state):
    state.primary.write_text("{truncated", encoding="utf-8")
    data = user_data.load_user_data()
    assert data["preferences"]["translation_mode"] == "online"
    assert data["last_session"]["pdf_path"] == ""


def test_corrupt_primary_falls_back_to_legacy_file(state):
    state.primary.write_text("not json", encoding="utf-8")
    state.legacy.write_text(json.dumps({"preferences": {"learning_language": "fr"}}), encoding="utf-8")
    assert user_data.load_user_data()["preferences"]["learning_language"] == "fr"


def test_primary_wins_over_legacy(state):
    state.primary.write_text(json.dumps({"preferences": {"learning_language": "it"}}), encoding="utf-8")
    state.legacy.write_text(json.dumps({"preferences": {"learning_language": "fr"}}), encoding="utf-8")
    assert user_data.load_user_data()["preferences"]["learning_language"] == "it"


@pytest.mark.parametrize("content", ["[]", '"text"', "42", "null"])
def test_non_dict_json_is_ignored(state, content):
    state.primary.write_text(content, encoding="utf-8")
    assert user_data.load_user_data()["version"] == 2


def test_bad_values_are_normalised(state):
    state.primary.write_text(
        json.dumps(
            {
                "preferences": {
                    "learning_language": "klingon",
                    "native_language": "EN ",
                    "theme_mode": "DARK",
                    "video_playback_speed": 0,
                    "prefetch_enabled": 0,
                },
                "analytics": {"cards_added_total": "7", "cards_added_by_day": [], "vocabulary_seen": "nope"},
                "progress": {"completed_pages": [], "completed_videos": {"a.mp4": True}},
                "usage_time": {"sessions": "x", "total_seconds": None, "last_activity_timestamp": None},
                "onboarding": "yes",
                "recent_files": None,
            }
        ),
        encoding="utf-8",
    )
    data = user_data.load_user_data()
    assert data["preferences"] == {
        "learning_language": "es",  # unsupported code falls back
        "native_language": "en",
        "translation_mode": "online",
        "video_playback_speed": 1.0,
        "theme_mode": "dark",
        "prefetch_enabled": False,
    }
    assert data["analytics"] == {"cards_added_total": 7, "cards_added_by_day": {}, "vocabulary_seen": []}
    assert data["progress"] == {"completed_pages": {}, "completed_videos": {"a.mp4": True}}
    assert data["usage_time"] == {"sessions": [], "total_seconds": 0, "last_activity_timestamp": ""}
    assert data["onboarding"] == {"dismissed": False}
    assert data["recent_files"] == []


def test_unknown_top_level_keys_survive_loading(state):
    state.primary.write_text(json.dumps({"future_feature": {"x": 1}}), encoding="utf-8")
    assert user_data.load_user_data()["future_feature"] == {"x": 1}


def test_save_then_load_round_trip_with_flush(qapp, state):
    data = user_data.load_user_data()
    data["recent_files"] = [{"path": "C:/libros/ñandú.pdf", "type": "pdf", "name": "ñandú.pdf", "page_index": 3}]
    data["analytics"]["vocabulary_seen"] = ["猫", "niño"]
    user_data.save_user_data(data)
    user_data.flush_user_data()
    assert not state.primary.with_suffix(".tmp").exists()
    reloaded = user_data.load_user_data()
    assert reloaded["recent_files"] == data["recent_files"]
    assert reloaded["analytics"]["vocabulary_seen"] == ["猫", "niño"]


def test_save_snapshots_payload_so_later_mutation_is_not_written(qapp, state, monkeypatch):
    written = []
    monkeypatch.setattr(user_data, "_write_snapshot", lambda snap: written.append(snap))
    data = {"analytics": {"vocabulary_seen": ["a"]}, "usage_time": {"sessions": []}}
    user_data.save_user_data(data)
    data["analytics"]["vocabulary_seen"].append("b")  # mutate before the worker runs
    user_data.flush_user_data()
    assert written == [{"analytics": {"vocabulary_seen": ["a"]}, "usage_time": {"sessions": []}}]


def test_failed_background_write_is_logged_not_raised(qapp, state, monkeypatch, caplog):
    def boom(snapshot):
        raise OSError("disk full")

    monkeypatch.setattr(user_data, "_write_snapshot", boom)
    user_data._SaveWorker({"x": 1}).run()
    assert "Background save failed" in caplog.text


def test_final_flush_failure_is_logged_not_raised(qapp, state, monkeypatch, caplog):
    def boom(snapshot):
        raise OSError("disk full")

    monkeypatch.setattr(user_data, "_write_snapshot", boom)
    user_data.flush_user_data({"x": 1})
    assert "Final save failed" in caplog.text


def test_write_snapshot_is_atomic_and_keeps_old_file_on_failure(state, monkeypatch):
    user_data._write_snapshot({"version": 2, "marker": "old"})
    monkeypatch.setattr(user_data.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("locked")))
    with pytest.raises(OSError):
        user_data._write_snapshot({"version": 2, "marker": "new"})
    assert json.loads(state.primary.read_text(encoding="utf-8"))["marker"] == "old"
