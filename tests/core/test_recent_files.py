"""Recent-files bookkeeping for page-based (PDF/EPUB) and time-based (video) files."""

from __future__ import annotations

from immersion_app.core.recent_files import add_recent_file, format_position_metadata


def test_epub_entry_stores_page_and_chapter_location():
    data: dict = {}

    add_recent_file(data, "C:/b/libro.epub", "epub", {"page_index": 7, "chapter": 2, "chapter_page": 3})

    entry = data["recent_files"][0]
    assert entry["type"] == "epub"
    assert (entry["page_index"], entry["chapter"], entry["chapter_page"]) == (7, 2, 3)
    assert "video_position_ms" not in entry


def test_pdf_entry_has_no_chapter_keys():
    data: dict = {}

    add_recent_file(data, "C:/b/libro.pdf", "pdf", {"page_index": 4})

    assert "chapter" not in data["recent_files"][0]
    assert data["recent_files"][0]["page_index"] == 4


def test_video_entry_still_uses_video_position():
    data: dict = {}

    add_recent_file(data, "C:/b/v.mp4", "video", {"video_position_ms": 5000})

    assert data["recent_files"][0]["video_position_ms"] == 5000


def test_reopening_replaces_entry_and_updates_position():
    data: dict = {}
    add_recent_file(data, "C:/b/libro.epub", "epub", {"page_index": 1, "chapter": 0, "chapter_page": 1})
    add_recent_file(data, "C:/b/libro.epub", "epub", {"page_index": 9, "chapter": 1, "chapter_page": 2})

    assert len(data["recent_files"]) == 1
    assert data["recent_files"][0]["page_index"] == 9


def test_format_position_metadata_pages_and_time():
    assert format_position_metadata("epub", page_index=41) == "Page 42"
    assert format_position_metadata("pdf", page_index=0) == "Page 1"
    assert format_position_metadata("video", video_position_ms=83000) == "1:23"
