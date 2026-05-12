"""Tests for ContentBrowserManager."""

import unittest
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from immersion_app.core.content_browser_manager import ContentBrowserManager


class SignalCapture(QObject):
    """Helper to capture signals."""
    def __init__(self):
        super().__init__()
        self.signals = []

    def capture(self, *args):
        self.signals.append(args)


class TestContentBrowserManager(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.user_data = {}
        self.manager = ContentBrowserManager(self.user_data)

    def test_initialization_creates_section(self):
        """Manager creates imported_content section if missing."""
        self.assertIn("imported_content", self.user_data)
        self.assertIn("items", self.user_data["imported_content"])
        self.assertEqual(self.user_data["imported_content"]["items"], [])

    def test_add_content_pdf(self):
        """Add PDF content to library."""
        capture = SignalCapture()
        self.manager.content_added.connect(capture.capture)

        item = self.manager.add_content(
            file_path="C:\\test\\book.pdf",
            content_type="pdf",
            page_count=150
        )

        # Check item returned
        self.assertEqual(item["type"], "pdf")
        self.assertEqual(item["page_count"], 150)
        self.assertIn("name", item)
        self.assertIn("preview_hash", item)
        self.assertIn("added_at", item)

        # Check stored in user_data
        self.assertEqual(len(self.user_data["imported_content"]["items"]), 1)

        # Check signal emitted
        self.assertEqual(len(capture.signals), 1)
        emitted_item = capture.signals[0][0]
        self.assertEqual(emitted_item["type"], "pdf")

    def test_add_content_video(self):
        """Add video content to library."""
        item = self.manager.add_content(
            file_path="C:\\test\\lesson.mp4",
            content_type="video",
            duration_ms=7200000,
            last_position={"video_position_ms": 120000}
        )

        self.assertEqual(item["type"], "video")
        self.assertEqual(item["duration_ms"], 7200000)
        self.assertEqual(item["last_position"]["video_position_ms"], 120000)

    def test_add_duplicate_updates_existing(self):
        """Adding duplicate content updates existing item."""
        # Add initial
        self.manager.add_content(
            file_path="C:\\test\\book.pdf",
            content_type="pdf",
            page_count=100
        )

        capture = SignalCapture()
        self.manager.content_updated.connect(capture.capture)

        # Add again with different page count
        item = self.manager.add_content(
            file_path="C:\\test\\book.pdf",
            content_type="pdf",
            page_count=150
        )

        # Should only have one item
        self.assertEqual(len(self.user_data["imported_content"]["items"]), 1)

        # Should be updated
        self.assertEqual(item["page_count"], 150)

        # Should emit content_updated signal
        self.assertEqual(len(capture.signals), 1)

    def test_get_content_by_path(self):
        """Get content item by file path."""
        self.manager.add_content(
            file_path="C:\\test\\book.pdf",
            content_type="pdf",
            page_count=150
        )

        item = self.manager.get_content_by_path("C:\\test\\book.pdf")
        self.assertIsNotNone(item)
        self.assertEqual(item["type"], "pdf")
        self.assertEqual(item["page_count"], 150)

        # Non-existent path
        item = self.manager.get_content_by_path("C:\\test\\missing.pdf")
        self.assertIsNone(item)

    def test_remove_content(self):
        """Remove content from library."""
        self.manager.add_content(
            file_path="C:\\test\\book.pdf",
            content_type="pdf"
        )

        capture = SignalCapture()
        self.manager.content_removed.connect(capture.capture)

        result = self.manager.remove_content("C:\\test\\book.pdf")

        self.assertTrue(result)
        self.assertEqual(len(self.user_data["imported_content"]["items"]), 0)
        self.assertEqual(len(capture.signals), 1)

    def test_remove_nonexistent_returns_false(self):
        """Removing non-existent content returns False."""
        result = self.manager.remove_content("C:\\test\\missing.pdf")
        self.assertFalse(result)

    def test_get_all_content(self):
        """Get all content items."""
        self.manager.add_content("C:\\test\\book1.pdf", "pdf")
        self.manager.add_content("C:\\test\\book2.pdf", "pdf")
        self.manager.add_content("C:\\test\\video.mp4", "video")

        items = self.manager.get_all_content()
        self.assertEqual(len(items), 3)

    def test_content_exists(self):
        """Check if content exists in library."""
        self.manager.add_content("C:\\test\\book.pdf", "pdf")

        self.assertTrue(self.manager.content_exists("C:\\test\\book.pdf"))
        self.assertFalse(self.manager.content_exists("C:\\test\\missing.pdf"))

    def test_update_last_position(self):
        """Update last position for content."""
        self.manager.add_content(
            file_path="C:\\test\\book.pdf",
            content_type="pdf",
            last_position={"page_index": 0}
        )

        capture = SignalCapture()
        self.manager.content_updated.connect(capture.capture)

        self.manager.update_last_position(
            "C:\\test\\book.pdf",
            {"page_index": 5}
        )

        item = self.manager.get_content_by_path("C:\\test\\book.pdf")
        self.assertEqual(item["last_position"]["page_index"], 5)
        self.assertEqual(len(capture.signals), 1)

    def test_path_normalization(self):
        """Paths are normalized for consistent storage."""
        # Add with different path formats
        self.manager.add_content("C:\\test\\book.pdf", "pdf")

        # Should find with normalized path
        item = self.manager.get_content_by_path("c:\\TEST\\book.pdf")
        self.assertIsNotNone(item)

    def test_preview_hash_deterministic(self):
        """Preview hash is deterministic based on file path."""
        item1 = self.manager.add_content("C:\\test\\book.pdf", "pdf")
        self.manager.remove_content("C:\\test\\book.pdf")
        item2 = self.manager.add_content("C:\\test\\book.pdf", "pdf")

        self.assertEqual(item1["preview_hash"], item2["preview_hash"])


if __name__ == "__main__":
    unittest.main()
