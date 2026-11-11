"""Unit tests for UsageTimeTracker state manager."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from immersion_app.core.usage_time_tracker import UsageTimeTracker


@pytest.fixture
def empty_user_data():
    """Provide empty user data dict."""
    return {
        "usage_time": {
            "sessions": [],
            "total_seconds": 0,
            "last_activity_timestamp": "",
        }
    }


@pytest.fixture
def populated_user_data():
    """Provide user data with some usage sessions."""
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    return {
        "usage_time": {
            "sessions": [
                {
                    "file_path": os.path.normcase(os.path.abspath("C:\\test\\book.pdf")),
                    "file_type": "pdf",
                    "start_time": yesterday.isoformat(),
                    "end_time": (yesterday + timedelta(minutes=30)).isoformat(),
                    "duration_seconds": 1800,
                    "metadata": {
                        "source_name": "book.pdf",
                        "start_location": "Page 1",
                        "end_location": "Page 10",
                    }
                },
                {
                    "file_path": os.path.normcase(os.path.abspath("C:\\test\\video.mp4")),
                    "file_type": "video",
                    "start_time": today.isoformat(),
                    "end_time": (today + timedelta(minutes=15)).isoformat(),
                    "duration_seconds": 900,
                    "metadata": {
                        "source_name": "video.mp4",
                        "start_location": "00:00:00",
                        "end_location": "00:15:00",
                    }
                },
            ],
            "total_seconds": 2700,
            "last_activity_timestamp": today.isoformat(),
        }
    }


class TestUsageTimeTrackerInitialization:
    """Test UsageTimeTracker initialization."""

    def test_initialization_with_empty_user_data(self, empty_user_data):
        """Ensure usage_time section is created if missing."""
        tracker = UsageTimeTracker(empty_user_data)
        assert "usage_time" in tracker._user_data
        assert "sessions" in tracker._user_data["usage_time"]
        assert "total_seconds" in tracker._user_data["usage_time"]
        assert "last_activity_timestamp" in tracker._user_data["usage_time"]

    def test_initialization_without_usage_time_section(self):
        """Ensure usage_time section is created when not present."""
        user_data = {}
        tracker = UsageTimeTracker(user_data)
        assert "usage_time" in user_data
        assert isinstance(user_data["usage_time"]["sessions"], list)
        assert user_data["usage_time"]["total_seconds"] == 0

    def test_initialization_with_invalid_usage_data(self):
        """Handle invalid usage_time data gracefully."""
        user_data = {
            "usage_time": {
                "sessions": "invalid",  # Should be list
                "total_seconds": "invalid",  # Should be int
            }
        }
        tracker = UsageTimeTracker(user_data)
        assert isinstance(user_data["usage_time"]["sessions"], list)
        assert isinstance(user_data["usage_time"]["total_seconds"], int)


class TestSessionTracking:
    """Test session tracking."""

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_session_start_on_document_loaded(self, mock_save, empty_user_data):
        """Verify session starts when document is loaded."""
        tracker = UsageTimeTracker(empty_user_data)
        signal_spy = Mock()
        tracker.session_started.connect(signal_spy)

        tracker.on_document_loaded("C:\\test\\book.pdf", 100)

        signal_spy.assert_called_once()
        args = signal_spy.call_args[0]
        assert args[0] == "C:\\test\\book.pdf"
        assert args[1] == "pdf"
        assert tracker._session_start_time is not None

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_epub_session_is_typed_epub_and_records_page_metrics(self, mock_save, empty_user_data):
        tracker = UsageTimeTracker(empty_user_data)
        signal_spy = Mock()
        tracker.session_started.connect(signal_spy)

        tracker.on_document_loaded("C:/test/libro.EPUB", 40)
        tracker.set_pdf_page_index(3)
        tracker.set_pdf_page_index(8)

        assert signal_spy.call_args[0][1] == "epub"
        assert tracker._current_file_type == "epub"
        assert tracker._start_page_index == 3
        assert tracker._current_page_index == 8

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_session_end_on_document_closed(self, mock_save, empty_user_data):
        """Verify session ends when document is closed."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)

        # Start session
        tracker.on_document_loaded("C:\\test\\book.pdf", 100)

        # Record some activity
        tracker.record_activity()
        time.sleep(0.1)  # Small delay to ensure different timestamps
        tracker.record_activity()

        # End session
        signal_spy = Mock()
        tracker.session_ended.connect(signal_spy)
        tracker.on_document_closed()

        # Should have called save_user_data
        mock_save.assert_called()

        # Should have emitted session_ended signal
        signal_spy.assert_called_once()

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_video_session_tracking(self, mock_save, empty_user_data):
        """Test video session tracking."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)

        # Start video session
        tracker.on_video_loaded("C:\\test\\video.mp4")
        assert tracker._current_file_type == "video"

        # Record activity
        tracker.record_activity()

        # End session
        tracker.on_video_closed()
        mock_save.assert_called()

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_session_finalization_saves_data(self, mock_save, empty_user_data):
        """Verify session finalization persists data."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        signal_spy = Mock()
        tracker.session_ended.connect(signal_spy)

        tracker.on_document_loaded("C:\\test\\book.pdf")
        tracker.record_activity()
        tracker.finalize_current_session()

        signal_spy.assert_called_once()
        mock_save.assert_called_once()

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_no_save_without_activity(self, mock_save, empty_user_data):
        """Don't save session if no activity was recorded."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)

        tracker.on_document_loaded("C:\\test\\book.pdf")
        # Don't record any activity
        tracker.finalize_current_session()

        # Should not save if no activity
        mock_save.assert_not_called()


class TestActivityRecording:
    """Test activity recording."""

    def test_activity_only_when_focused(self, empty_user_data):
        """Activity should only be recorded when window is focused."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.on_document_loaded("C:\\test\\book.pdf")

        # Not focused - no activity
        tracker.set_window_focused(False)
        tracker.record_activity()
        assert len(tracker._activity_buffer) == 0

        # Focused - activity recorded
        tracker.set_window_focused(True)
        tracker.record_activity()
        assert len(tracker._activity_buffer) == 1

    def test_activity_buffer_accumulation(self, empty_user_data):
        """Activity buffer should accumulate timestamps."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\\test\\book.pdf")

        # Record multiple activities
        tracker.record_activity()
        tracker.record_activity()
        tracker.record_activity()

        assert len(tracker._activity_buffer) == 3

    def test_activity_buffer_cleared_on_session_end(self, empty_user_data):
        """Activity buffer should be cleared when session ends."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\\test\\book.pdf")

        tracker.record_activity()
        assert len(tracker._activity_buffer) > 0

        # Start new session
        tracker.on_document_loaded("C:\\test\\other.pdf")
        assert len(tracker._activity_buffer) == 0


class TestDurationCalculation:
    """Test the 2-minute window duration calculation."""

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_single_activity_creates_2_minute_window(self, mock_save, empty_user_data):
        """Single activity should create a 2-minute window."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\\test\\book.pdf")

        tracker.record_activity()
        tracker.finalize_current_session()

        # Should have ~120 seconds (2 minutes)
        session = empty_user_data["usage_time"]["sessions"][0]
        assert session["duration_seconds"] == 120
        assert session["elapsed_seconds"] >= 120
        assert session["metadata"]["start_page_index"] == 0
        assert session["metadata"]["end_page_index"] == 0
        assert session["metadata"]["pages_advanced"] == 0

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_overlapping_windows_are_merged(self, mock_save, empty_user_data):
        """Overlapping 2-minute windows should be merged."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\\test\\book.pdf")

        # Record two activities within 2 minutes of each other
        now = datetime.now()
        tracker._activity_buffer.append(now)
        tracker._activity_buffer.append(now + timedelta(seconds=30))

        tracker.finalize_current_session()

        # Windows should overlap and merge
        # First window: [now-60, now+60]
        # Second window: [now+30-60, now+30+60] = [now-30, now+90]
        # Merged: [now-60, now+90] = 150 seconds
        session = empty_user_data["usage_time"]["sessions"][0]
        assert session["duration_seconds"] == 150

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_separate_windows_not_merged(self, mock_save, empty_user_data):
        """Non-overlapping windows should remain separate."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\\test\\book.pdf")

        # Record two activities more than 2 minutes apart
        now = datetime.now()
        tracker._activity_buffer.append(now)
        tracker._activity_buffer.append(now + timedelta(minutes=5))

        tracker.finalize_current_session()

        # Should have two separate 2-minute windows = 240 seconds
        session = empty_user_data["usage_time"]["sessions"][0]
        assert session["duration_seconds"] == 240


class TestStatisticsQueries:
    """Test statistics query methods."""

    def test_get_total_usage_seconds(self, populated_user_data):
        """Query total usage time."""
        tracker = UsageTimeTracker(populated_user_data)
        total = tracker.get_total_usage_seconds()
        assert total == 2700

    def test_get_today_usage_seconds(self, populated_user_data):
        """Query today's usage time."""
        tracker = UsageTimeTracker(populated_user_data)
        today_usage = tracker.get_today_usage_seconds()
        # Only the second session (video) is from today
        assert today_usage == 900

    def test_get_file_usage_seconds(self, populated_user_data):
        """Query usage time for a specific file."""
        tracker = UsageTimeTracker(populated_user_data)
        pdf_usage = tracker.get_file_usage_seconds("C:\\test\\book.pdf")
        assert pdf_usage == 1800

    def test_get_file_usage_seconds_nonexistent_file(self, empty_user_data):
        """Query for nonexistent file should return 0."""
        tracker = UsageTimeTracker(empty_user_data)
        usage = tracker.get_file_usage_seconds("C:\\nonexistent.pdf")
        assert usage == 0


class TestEdgeCases:
    """Test edge cases."""

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_rapid_file_switching(self, mock_save, empty_user_data):
        """Test rapid switching between files."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)

        # Load first file
        tracker.on_document_loaded("C:\\test\\book1.pdf")
        tracker.record_activity()

        # Immediately switch to second file
        tracker.on_document_loaded("C:\\test\\book2.pdf")
        tracker.record_activity()

        # First session should have been finalized
        assert mock_save.call_count >= 1

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_path_normalization(self, mock_save, empty_user_data):
        """Windows path case handling."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)

        # Load with different case
        tracker.on_document_loaded("C:\\Test\\Book.pdf")
        tracker.record_activity()
        tracker.finalize_current_session()

        # Query with different case should still work
        normalized = os.path.normcase(os.path.abspath("C:\\Test\\Book.pdf"))
        normalized_alt = os.path.normcase(os.path.abspath("c:\\test\\book.pdf"))

        # On Windows, these should be the same
        if os.name == "nt":
            assert normalized == normalized_alt
            usage = tracker.get_file_usage_seconds("c:\\test\\book.pdf")
            assert usage > 0

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_session_metadata(self, mock_save, empty_user_data):
        """Verify session metadata is correctly stored."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)

        tracker.on_document_loaded("C:\\test\\book.pdf")
        tracker.set_pdf_page_index(0)
        tracker.set_pdf_page_index(4)
        tracker.update_location("Page 5")
        tracker.record_activity()
        tracker.finalize_current_session()

        session = empty_user_data["usage_time"]["sessions"][0]
        assert session["metadata"]["source_name"] == "book.pdf"
        assert session["metadata"]["start_location"] == "Page 1"
        assert session["metadata"]["end_location"] == "Page 5"
        assert session["metadata"]["start_page_index"] == 0
        assert session["metadata"]["end_page_index"] == 4
        assert session["metadata"]["pages_advanced"] == 4

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_video_session_metadata(self, mock_save, empty_user_data):
        """Verify machine-readable video session metrics are stored."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)

        tracker.on_video_loaded("C:\\test\\video.mp4")
        tracker.set_video_position_ms(0)
        tracker.set_video_position_ms(120000)
        tracker.record_activity()
        tracker.finalize_current_session()

        session = empty_user_data["usage_time"]["sessions"][0]
        assert session["metadata"]["start_position_ms"] == 0
        assert session["metadata"]["end_position_ms"] == 120000
        assert session["metadata"]["minutes_advanced"] == 2.0


class TestDataPersistence:
    """Test data structure and persistence."""

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_session_timestamp_format(self, mock_save, empty_user_data):
        """Ensure timestamps are ISO format."""
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\\test\\book.pdf")
        tracker.record_activity()
        tracker.finalize_current_session()

        session = empty_user_data["usage_time"]["sessions"][0]

        # Should have valid ISO timestamps
        assert "start_time" in session
        assert "end_time" in session
        assert "elapsed_seconds" in session

        # Should be parseable as ISO datetime
        start = datetime.fromisoformat(session["start_time"])
        end = datetime.fromisoformat(session["end_time"])
        assert isinstance(start, datetime)
        assert isinstance(end, datetime)

    def test_loaded_data_compatibility(self, populated_user_data):
        """Ensure tracker works with pre-existing data."""
        tracker = UsageTimeTracker(populated_user_data)

        # Should find pre-existing sessions
        total = tracker.get_total_usage_seconds()
        assert total == 2700

        # Should calculate today's usage correctly
        today_usage = tracker.get_today_usage_seconds()
        assert today_usage == 900


class TestIdleAndResume:
    """Regression tests for idle handling (tracking must resume after a break)."""

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_activity_after_idle_starts_new_segment(self, mock_save, empty_user_data):
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\test\book.pdf")
        tracker.record_activity()

        # Simulate 3 minutes of idleness, then the inactivity check.
        tracker._activity_buffer = [datetime.now() - timedelta(minutes=3)]
        tracker._check_inactivity()
        assert not tracker.is_currently_active()
        assert len(empty_user_data["usage_time"]["sessions"]) == 1

        # The user comes back: activity must count again on the same file.
        tracker.record_activity()
        assert tracker.is_currently_active()
        assert len(tracker._activity_buffer) == 1

        tracker.finalize_current_session()
        sessions = empty_user_data["usage_time"]["sessions"]
        assert len(sessions) == 2
        assert sessions[1]["file_path"] == sessions[0]["file_path"]

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_idle_segment_keeps_page_progress_continuous(self, mock_save, empty_user_data):
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\test\book.pdf")
        tracker.set_pdf_page_index(2)
        tracker.record_activity()
        tracker.set_pdf_page_index(3)
        tracker._activity_buffer = [datetime.now() - timedelta(minutes=3)]
        tracker._check_inactivity()

        tracker.set_pdf_page_index(5)
        tracker.record_activity()
        tracker.finalize_current_session()

        first, second = empty_user_data["usage_time"]["sessions"]
        assert (first["metadata"]["start_page_index"], first["metadata"]["end_page_index"]) == (2, 3)
        assert (second["metadata"]["start_page_index"], second["metadata"]["end_page_index"]) == (3, 5)

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_restored_page_is_not_counted_as_progress(self, mock_save, empty_user_data):
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\test\book.pdf")
        tracker.set_pdf_page_index(40)  # reopened at a saved position
        tracker.record_activity()
        tracker.finalize_current_session()

        metadata = empty_user_data["usage_time"]["sessions"][0]["metadata"]
        assert metadata["start_page_index"] == 40
        assert metadata["pages_advanced"] == 0

    def test_no_activity_without_open_file(self, empty_user_data):
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.record_activity()
        assert tracker._activity_buffer == []
        assert not tracker.is_currently_active()

    def test_losing_focus_marks_idle_immediately(self, empty_user_data):
        tracker = UsageTimeTracker(empty_user_data)
        statuses = []
        tracker.active_status_changed.connect(statuses.append)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\test\book.pdf")
        tracker.record_activity()
        tracker.set_window_focused(False)
        assert statuses == [True, False]


class TestMidnightSplit:
    """Time is credited to the calendar day it happened on."""

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_segment_spanning_midnight_is_split(self, mock_save, empty_user_data):
        tracker = UsageTimeTracker(empty_user_data)
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\test\book.pdf")

        midnight = datetime.combine(datetime.now().date(), datetime.min.time())
        tracker._session_start_time = midnight - timedelta(minutes=5)
        # Activities every 30 s from 23:58 to 00:02 -> one merged window 23:57..00:03
        tracker._activity_buffer = [midnight + timedelta(seconds=offset) for offset in range(-120, 121, 30)]
        tracker.finalize_current_session()

        sessions = empty_user_data["usage_time"]["sessions"]
        assert len(sessions) == 2
        assert [s["duration_seconds"] for s in sessions] == [180, 180]
        assert datetime.fromisoformat(sessions[0]["start_time"]).date() == (midnight - timedelta(days=1)).date()
        assert datetime.fromisoformat(sessions[1]["start_time"]).date() == midnight.date()
        assert empty_user_data["usage_time"]["total_seconds"] == 360
