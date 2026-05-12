"""Unit tests for CompletionTracker state manager."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QObject, SignalInstance

from immersion_app.core.completion_tracker import CompletionTracker


@pytest.fixture
def temp_user_data_file(tmp_path):
    """Create a temporary user data file for testing."""
    test_file = tmp_path / "test_user_data.json"
    return str(test_file)


@pytest.fixture
def empty_user_data():
    """Provide empty user data dict."""
    return {
        "progress": {
            "completed_pages": {},
            "completed_videos": {},
        }
    }


@pytest.fixture
def populated_user_data():
    """Provide user data with some completion data."""
    return {
        "progress": {
            "completed_pages": {
                os.path.normcase(os.path.abspath("C:\\test\\book.pdf")): [
                    {"page": 0, "completed_at": "2026-01-01T10:00:00"},
                    {"page": 5, "completed_at": "2026-01-01T11:00:00"},
                ]
            },
            "completed_videos": {
                os.path.normcase(os.path.abspath("C:\\test\\video.mp4")): {
                    "completed_at": "2026-01-01T12:00:00"
                }
            },
        }
    }


class TestCompletionTrackerInitialization:
    """Test CompletionTracker initialization."""

    def test_initialization_with_empty_user_data(self, empty_user_data):
        """Ensure progress section is created if missing."""
        tracker = CompletionTracker(empty_user_data)
        assert "progress" in tracker._user_data
        assert "completed_pages" in tracker._user_data["progress"]
        assert "completed_videos" in tracker._user_data["progress"]

    def test_initialization_without_progress_section(self):
        """Ensure progress section is created when not present."""
        user_data = {}
        tracker = CompletionTracker(user_data)
        assert "progress" in user_data
        assert isinstance(user_data["progress"]["completed_pages"], dict)
        assert isinstance(user_data["progress"]["completed_videos"], dict)

    def test_initialization_with_invalid_progress_data(self):
        """Handle invalid progress data gracefully."""
        user_data = {
            "progress": {
                "completed_pages": "invalid",  # Should be dict
                "completed_videos": None,  # Should be dict
            }
        }
        tracker = CompletionTracker(user_data)
        assert isinstance(user_data["progress"]["completed_pages"], dict)
        assert isinstance(user_data["progress"]["completed_videos"], dict)


class TestPageCompletion:
    """Test page completion tracking."""

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_mark_page_complete_emits_signal(self, mock_save, empty_user_data, qtbot):
        """Verify signal emission when marking page complete."""
        tracker = CompletionTracker(empty_user_data)
        signal_spy = Mock()
        tracker.completion_changed.connect(signal_spy)

        tracker.mark_page_complete("C:\\test\\book.pdf", 0)

        signal_spy.assert_called_once()
        args = signal_spy.call_args[0]
        assert args[0] == "C:\\test\\book.pdf"  # file_path
        assert args[1] == 0  # page_index
        assert args[2] is True  # is_complete

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_mark_page_complete_persists_data(self, mock_save, empty_user_data):
        """Verify save_user_data is called."""
        tracker = CompletionTracker(empty_user_data)
        tracker.mark_page_complete("C:\\test\\book.pdf", 5)

        mock_save.assert_called_once_with(empty_user_data)

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_is_page_complete_returns_correct_state(self, mock_save, empty_user_data):
        """Query correctness."""
        tracker = CompletionTracker(empty_user_data)
        assert not tracker.is_page_complete("C:\\test\\book.pdf", 0)

        tracker.mark_page_complete("C:\\test\\book.pdf", 0)
        assert tracker.is_page_complete("C:\\test\\book.pdf", 0)

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_unmark_page_complete(self, mock_save, empty_user_data, qtbot):
        """Toggle off functionality."""
        tracker = CompletionTracker(empty_user_data)
        signal_spy = Mock()
        tracker.completion_changed.connect(signal_spy)

        # Mark complete
        tracker.mark_page_complete("C:\\test\\book.pdf", 0)
        assert tracker.is_page_complete("C:\\test\\book.pdf", 0)

        # Unmark
        tracker.unmark_page_complete("C:\\test\\book.pdf", 0)
        assert not tracker.is_page_complete("C:\\test\\book.pdf", 0)

        # Check signal emission
        assert signal_spy.call_count == 2
        unmark_args = signal_spy.call_args[0]
        assert unmark_args[2] is False  # is_complete = False

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_path_normalization(self, mock_save, empty_user_data):
        """Windows path case handling."""
        tracker = CompletionTracker(empty_user_data)

        # Mark with different case variations
        tracker.mark_page_complete("C:\\Test\\Book.pdf", 0)

        # Should find it regardless of case (on Windows)
        normalized = os.path.normcase(os.path.abspath("C:\\Test\\Book.pdf"))
        normalized_alt = os.path.normcase(os.path.abspath("c:\\test\\book.pdf"))

        # On Windows, these should be the same
        if os.name == "nt":
            assert normalized == normalized_alt
            assert tracker.is_page_complete("c:\\test\\book.pdf", 0)

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_duplicate_completion_prevention(self, mock_save, empty_user_data):
        """No duplicate entries when marking same page multiple times."""
        tracker = CompletionTracker(empty_user_data)

        # Mark same page twice
        tracker.mark_page_complete("C:\\test\\book.pdf", 0)
        tracker.mark_page_complete("C:\\test\\book.pdf", 0)

        # Should only have one entry
        normalized_path = tracker._normalize_path("C:\\test\\book.pdf")
        pages = empty_user_data["progress"]["completed_pages"][normalized_path]
        assert len(pages) == 1

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_get_completed_pages(self, mock_save, empty_user_data):
        """Get all completed pages for a file."""
        tracker = CompletionTracker(empty_user_data)

        # Mark several pages
        tracker.mark_page_complete("C:\\test\\book.pdf", 5)
        tracker.mark_page_complete("C:\\test\\book.pdf", 0)
        tracker.mark_page_complete("C:\\test\\book.pdf", 10)

        completed = tracker.get_completed_pages("C:\\test\\book.pdf")
        assert completed == [0, 5, 10]  # Should be sorted

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_get_completion_percentage(self, mock_save, empty_user_data):
        """Calculate progress percentage."""
        tracker = CompletionTracker(empty_user_data)

        # Mark 3 out of 10 pages
        tracker.mark_page_complete("C:\\test\\book.pdf", 0)
        tracker.mark_page_complete("C:\\test\\book.pdf", 1)
        tracker.mark_page_complete("C:\\test\\book.pdf", 2)

        percentage = tracker.get_completion_percentage("C:\\test\\book.pdf", 10)
        assert percentage == 30.0

    def test_get_completion_percentage_zero_pages(self, empty_user_data):
        """Handle edge case of zero total pages."""
        tracker = CompletionTracker(empty_user_data)
        percentage = tracker.get_completion_percentage("C:\\test\\book.pdf", 0)
        assert percentage == 0.0


class TestVideoCompletion:
    """Test video completion tracking."""

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_is_video_complete(self, mock_save, empty_user_data):
        """Query video completion state."""
        tracker = CompletionTracker(empty_user_data)
        assert not tracker.is_video_complete("C:\\test\\video.mp4")

        tracker.mark_video_complete("C:\\test\\video.mp4")
        assert tracker.is_video_complete("C:\\test\\video.mp4")

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_mark_video_complete_persists(self, mock_save, empty_user_data):
        """Verify video completion is saved."""
        tracker = CompletionTracker(empty_user_data)
        tracker.mark_video_complete("C:\\test\\video.mp4")

        mock_save.assert_called_once_with(empty_user_data)

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_unmark_video_complete(self, mock_save, empty_user_data):
        """Toggle off video completion."""
        tracker = CompletionTracker(empty_user_data)

        tracker.mark_video_complete("C:\\test\\video.mp4")
        assert tracker.is_video_complete("C:\\test\\video.mp4")

        tracker.unmark_video_complete("C:\\test\\video.mp4")
        assert not tracker.is_video_complete("C:\\test\\video.mp4")

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_video_duplicate_prevention(self, mock_save, empty_user_data):
        """No duplicate video entries."""
        tracker = CompletionTracker(empty_user_data)

        tracker.mark_video_complete("C:\\test\\video.mp4")
        tracker.mark_video_complete("C:\\test\\video.mp4")

        # Should only call save once for the duplicate
        assert mock_save.call_count == 1


class TestDataPersistence:
    """Test data structure and persistence."""

    @patch("immersion_app.core.completion_tracker.save_user_data")
    def test_completion_timestamp_format(self, mock_save, empty_user_data):
        """Ensure timestamp is ISO format."""
        tracker = CompletionTracker(empty_user_data)
        tracker.mark_page_complete("C:\\test\\book.pdf", 0)

        normalized_path = tracker._normalize_path("C:\\test\\book.pdf")
        page_entry = empty_user_data["progress"]["completed_pages"][normalized_path][0]

        # Should have completed_at timestamp
        assert "completed_at" in page_entry
        timestamp_str = page_entry["completed_at"]

        # Should be parseable as ISO datetime
        parsed = datetime.fromisoformat(timestamp_str)
        assert isinstance(parsed, datetime)

    def test_loaded_data_compatibility(self, populated_user_data):
        """Ensure tracker works with pre-existing data."""
        tracker = CompletionTracker(populated_user_data)

        # Should find pre-existing completions
        assert tracker.is_page_complete("C:\\test\\book.pdf", 0)
        assert tracker.is_page_complete("C:\\test\\book.pdf", 5)
        assert tracker.is_video_complete("C:\\test\\video.mp4")

        # Should get correct page list
        pages = tracker.get_completed_pages("C:\\test\\book.pdf")
        assert 0 in pages
        assert 5 in pages
