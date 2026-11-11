"""User data saving: ordered background saves and a synchronous flush on exit."""

from __future__ import annotations

import json

from immersion_app.core import user_data
from immersion_app.core.anki import DEFAULT_DECK_NAME


def test_saves_are_written_in_order_and_flush_waits(qapp, tmp_path, monkeypatch):
    target = tmp_path / "state" / "user.json"
    monkeypatch.setattr(user_data, "USER_STATE_PATH", target)
    payload = user_data.default_user_data()
    for i in range(20):
        payload["usage_time"]["total_seconds"] = i
        user_data.save_user_data(payload)
    user_data.flush_user_data()
    assert json.loads(target.read_text(encoding="utf-8"))["usage_time"]["total_seconds"] == 19


def test_flush_writes_final_payload_synchronously(qapp, tmp_path, monkeypatch):
    target = tmp_path / "state" / "user.json"
    monkeypatch.setattr(user_data, "USER_STATE_PATH", target)
    payload = user_data.default_user_data()
    payload["usage_time"]["total_seconds"] = 42
    user_data.flush_user_data(payload)
    assert json.loads(target.read_text(encoding="utf-8"))["usage_time"]["total_seconds"] == 42


def test_load_normalises_anki_and_keeps_prefetch_preference(tmp_path, monkeypatch):
    target = tmp_path / "user.json"
    target.write_text(
        json.dumps({"preferences": {"prefetch_enabled": False}, "anki": {"deck_name": ""}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(user_data, "USER_STATE_PATH", target)
    monkeypatch.setattr(user_data, "LEGACY_USER_STATE_PATH", tmp_path / "missing.json")
    loaded = user_data.load_user_data()
    assert loaded["preferences"]["prefetch_enabled"] is False
    assert loaded["anki"]["deck_name"] == DEFAULT_DECK_NAME
    assert loaded["onboarding"] == {"dismissed": False}
