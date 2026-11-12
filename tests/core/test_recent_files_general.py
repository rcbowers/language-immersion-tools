"""Tests for the recent-files list helpers."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

from immersion_app.core import recent_files as rf


def test_add_puts_newest_first():
    data = {}
    rf.add_recent_file(data, "a.pdf", "pdf", {"page_index": 1})
    rf.add_recent_file(data, "b.pdf", "pdf", {"page_index": 2})
    assert [f["name"] for f in data["recent_files"]] == ["b.pdf", "a.pdf"]


def test_readding_moves_to_top_without_duplicating(tmp_path):
    path = str(tmp_path / "book.pdf")
    data = {}
    rf.add_recent_file(data, path, "pdf", {"page_index": 1})
    rf.add_recent_file(data, str(tmp_path / "other.pdf"), "pdf", {})
    rf.add_recent_file(data, path, "pdf", {"page_index": 9})
    names = [f["name"] for f in data["recent_files"]]
    assert names == ["book.pdf", "other.pdf"]
    assert data["recent_files"][0]["page_index"] == 9


def test_duplicate_detected_across_relative_and_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = {}
    rf.add_recent_file(data, "book.pdf", "pdf", {})
    rf.add_recent_file(data, str(tmp_path / "book.pdf"), "pdf", {})
    assert len(data["recent_files"]) == 1


@pytest.mark.skipif(os.name != "nt", reason="case-insensitive paths are Windows-only")
def test_duplicate_detected_case_insensitively_on_windows(tmp_path):
    data = {}
    rf.add_recent_file(data, str(tmp_path / "Book.PDF"), "pdf", {})
    rf.add_recent_file(data, str(tmp_path / "book.pdf"), "pdf", {})
    assert len(data["recent_files"]) == 1


def test_list_is_capped():
    data = {}
    for i in range(rf.MAX_RECENT_FILES + 3):
        rf.add_recent_file(data, f"f{i}.pdf", "pdf", {})
    names = [f["name"] for f in data["recent_files"]]
    assert len(names) == rf.MAX_RECENT_FILES == 5
    assert names[0] == f"f{rf.MAX_RECENT_FILES + 2}.pdf"
    assert "f0.pdf" not in names


def test_position_fields_by_type():
    data = {}
    rf.add_recent_file(data, "a.pdf", "pdf", {"page_index": 7})
    rf.add_recent_file(data, "v.mp4", "video", {"video_position_ms": 4500})
    video, pdf = data["recent_files"]
    assert pdf["page_index"] == 7 and "video_position_ms" not in pdf
    assert video["video_position_ms"] == 4500 and "page_index" not in video


def test_missing_position_keys_default_to_zero():
    data = {}
    rf.add_recent_file(data, "a.pdf", "pdf", {})
    rf.add_recent_file(data, "v.mp4", "video", {})
    video, pdf = data["recent_files"]
    assert pdf["page_index"] == 0
    assert video["video_position_ms"] == 0


def test_get_hides_deleted_files_without_mutating(tmp_path):
    real = tmp_path / "real.pdf"
    real.write_bytes(b"x")
    data = {}
    rf.add_recent_file(data, str(real), "pdf", {})
    rf.add_recent_file(data, str(tmp_path / "gone.pdf"), "pdf", {})

    visible = rf.get_recent_files(data)
    assert [f["name"] for f in visible] == ["real.pdf"]
    assert len(data["recent_files"]) == 2
    assert len(rf.get_recent_files(data, validate_exists=False)) == 2


def test_get_with_no_data():
    assert rf.get_recent_files({}) == []


def test_remove(tmp_path):
    data = {}
    rf.add_recent_file(data, str(tmp_path / "a.pdf"), "pdf", {})
    rf.add_recent_file(data, str(tmp_path / "b.pdf"), "pdf", {})
    rf.remove_recent_file(data, str(tmp_path / "a.pdf"))
    assert [f["name"] for f in data["recent_files"]] == ["b.pdf"]
    rf.remove_recent_file(data, str(tmp_path / "never-added.pdf"))  # no error
    assert len(data["recent_files"]) == 1


class _FrozenNow(datetime):
    frozen = datetime(2026, 1, 1, 12, 0, 0)

    @classmethod
    def now(cls, tz=None):
        return cls.frozen


@pytest.mark.parametrize(
    "delta, expected",
    [
        (timedelta(seconds=59), "Just now"),
        (timedelta(seconds=60), "1 minute ago"),
        (timedelta(minutes=2), "2 minutes ago"),
        (timedelta(seconds=3599), "59 minutes ago"),
        (timedelta(hours=1), "1 hour ago"),
        (timedelta(hours=5), "5 hours ago"),
        (timedelta(days=1), "1 day ago"),
        (timedelta(days=3), "3 days ago"),
        (timedelta(weeks=1), "1 week ago"),
        (timedelta(weeks=2), "2 weeks ago"),
        (timedelta(days=30), "1 month ago"),
        (timedelta(days=65), "2 months ago"),
    ],
)
def test_format_time_ago_boundaries(monkeypatch, delta, expected):
    monkeypatch.setattr(rf, "datetime", _FrozenNow)
    stamp = (_FrozenNow.frozen - delta).isoformat()
    assert rf.format_time_ago(stamp) == expected


@pytest.mark.parametrize("bad", ["not a date", None, 123])
def test_format_time_ago_bad_input(bad):
    assert rf.format_time_ago(bad) == "Unknown"


def test_format_position_pdf_is_one_based():
    assert rf.format_position_metadata("pdf", page_index=0) == "Page 1"
    assert rf.format_position_metadata("pdf", page_index=41) == "Page 42"


@pytest.mark.parametrize(
    "ms, expected",
    [
        (0, "0:00"),
        (5_000, "0:05"),
        (65_000, "1:05"),
        (3_599_000, "59:59"),
        (3_600_000, "1:00:00"),
        (5_025_000, "1:23:45"),
    ],
)
def test_format_position_video(ms, expected):
    assert rf.format_position_metadata("video", video_position_ms=ms) == expected
