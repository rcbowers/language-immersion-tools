"""Tests for runtime data paths and legacy data migration."""

from __future__ import annotations

from pathlib import Path

from immersion_app.core import paths


def _make_legacy(root: Path) -> None:
    (root / "state").mkdir(parents=True)
    (root / "state" / paths.USER_STATE_PATH.name).write_text('{"version": 2}', encoding="utf-8")
    (root / "queue").mkdir()
    (root / "queue" / "queued_cards.json").write_text("[]", encoding="utf-8")


def test_data_root_honours_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(tmp_path / "custom"))
    assert paths.resolve_data_root() == tmp_path / "custom"


def test_data_root_defaults_outside_source_tree(monkeypatch):
    monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
    root = paths.resolve_data_root()
    assert paths.APP_NAME in str(root)
    assert paths.PROJECT_ROOT not in root.parents


def test_migrates_legacy_data_once(tmp_path):
    legacy = tmp_path / "legacy"
    target = tmp_path / "target"
    _make_legacy(legacy)

    assert paths.migrate_legacy_data(legacy, target) is True
    assert (target / "state" / paths.USER_STATE_PATH.name).read_text(encoding="utf-8") == '{"version": 2}'
    assert (target / "queue" / "queued_cards.json").exists()
    assert (legacy / "state").exists(), "legacy folder must be left in place"

    # Second run must not overwrite newer data.
    (target / "state" / paths.USER_STATE_PATH.name).write_text('{"version": 3}', encoding="utf-8")
    assert paths.migrate_legacy_data(legacy, target) is False
    assert (target / "state" / paths.USER_STATE_PATH.name).read_text(encoding="utf-8") == '{"version": 3}'


def test_no_migration_without_legacy_folder(tmp_path):
    assert paths.migrate_legacy_data(tmp_path / "missing", tmp_path / "target") is False
