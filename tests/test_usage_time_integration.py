"""Integration tests for usage time tracking.

Note: These tests require PySide6 to be installed.
Run with: python -m pytest tests/test_usage_time_integration.py
"""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

# Skip all tests if PySide6 is not available
pytest.importorskip("PySide6")

from immersion_app.core.usage_time_tracker import UsageTimeTracker
from immersion_app.core.pdf_service import PDFService
from immersion_app.core.video_service import VideoService
from immersion_app.core.selection_state import SelectionState
from immersion_app.core.translation_service import TranslationService


@pytest.fixture
def user_data():
    """Provide user data for testing."""
    return {
        "usage_time": {
            "sessions": [],
            "total_seconds": 0,
            "last_activity_timestamp": "",
        },
        "preferences": {
            "learning_language": "ja",
            "native_language": "en",
        }
    }


class TestPDFWorkflow:
    """Test usage tracking with PDF workflow."""

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_pdf_session_tracking(self, mock_save, user_data, qtbot, tmp_path):
        """Test complete PDF workflow with usage tracking."""
        # Create a simple PDF for testing
        import fitz
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Test content")
        doc.save(str(pdf_path))
        doc.close()

        # Initialize services
        pdf_service = PDFService()
        selection_state = SelectionState()
        tracker = UsageTimeTracker(user_data)

        # Connect signals (simulating main_window.py integration)
        pdf_service.document_loaded.connect(tracker.on_document_loaded)
        pdf_service.document_closed.connect(tracker.on_document_closed)
        selection_state.selection_changed.connect(lambda: tracker.record_activity())

        # Simulate user workflow
        tracker.set_window_focused(True)

        # Load PDF
        pdf_service.load_document(str(pdf_path))
        qtbot.wait(100)  # Wait for signal processing

        # Simulate user activity
        selection_state.set_manual_word("test")
        qtbot.wait(100)

        selection_state.set_manual_word("content")
        qtbot.wait(100)

        # Close PDF
        pdf_service.close_document()
        qtbot.wait(100)

        # Verify session was saved
        mock_save.assert_called()
        assert len(user_data["usage_time"]["sessions"]) == 1

        session = user_data["usage_time"]["sessions"][0]
        assert session["file_type"] == "pdf"
        assert os.path.normcase(session["file_path"]) == os.path.normcase(os.path.abspath(str(pdf_path)))
        assert session["duration_seconds"] > 0


class TestVideoWorkflow:
    """Test usage tracking with video workflow."""

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_video_session_tracking(self, mock_save, user_data, qtbot, tmp_path):
        """Test video workflow with usage tracking."""
        # Create a simple SRT file for testing
        srt_path = tmp_path / "test.srt"
        srt_path.write_text("1\n00:00:00,000 --> 00:00:02,000\nTest subtitle\n")

        # Initialize services
        video_service = VideoService()
        selection_state = SelectionState()
        tracker = UsageTimeTracker(user_data)

        # Note: VideoService doesn't have a video_loaded signal, so we simulate it
        video_path = str(tmp_path / "test.mp4")
        tracker.set_window_focused(True)
        tracker.on_video_loaded(video_path)

        # Simulate user activity
        selection_state.set_manual_word("test")
        qtbot.wait(100)

        tracker.record_activity()
        qtbot.wait(100)

        # Close video
        tracker.on_video_closed()
        qtbot.wait(100)

        # Verify session was saved
        mock_save.assert_called()
        assert len(user_data["usage_time"]["sessions"]) == 1

        session = user_data["usage_time"]["sessions"][0]
        assert session["file_type"] == "video"
        assert session["duration_seconds"] > 0


class TestSignalIntegration:
    """Test signal connections."""

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_translation_triggers_activity(self, mock_save, user_data, qtbot):
        """Test that translation completion triggers activity recording."""
        tracker = UsageTimeTracker(user_data)
        translation_service = TranslationService("ja", "en")

        # Connect translation signal
        translation_service.translation_ready.connect(lambda *_: tracker.record_activity())

        # Start a session
        tracker.set_window_focused(True)
        tracker.on_document_loaded("C:\\test\\book.pdf")

        # Clear activity buffer to test translation trigger
        tracker._activity_buffer.clear()

        # Simulate translation completion (cached, immediate)
        translation_service.translation_cache[("ja", "en", "test")] = "test translation"
        translation_service.translate_async("test")
        qtbot.wait(100)

        # Should have recorded activity
        assert len(tracker._activity_buffer) > 0


class TestFocusHandling:
    """Test window focus handling."""

    @patch("immersion_app.core.usage_time_tracker.save_user_data")
    def test_no_activity_when_unfocused(self, mock_save, user_data):
        """Verify activity is not recorded when window is unfocused."""
        tracker = UsageTimeTracker(user_data)
        tracker.on_document_loaded("C:\\test\\book.pdf")

        # Window not focused
        tracker.set_window_focused(False)
        tracker.record_activity()
        assert len(tracker._activity_buffer) == 0

        # Window focused
        tracker.set_window_focused(True)
        tracker.record_activity()
        assert len(tracker._activity_buffer) == 1
