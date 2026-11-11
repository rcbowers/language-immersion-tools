"""Tests for content browser widgets."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from immersion_app.core.content_browser_manager import ContentBrowserManager
from immersion_app.core.preview_generator import PreviewGenerator
from immersion_app.gui.widgets.content_browser_item import ContentBrowserItem
from immersion_app.gui.widgets.content_browser_grid import ContentBrowserGrid
from immersion_app.gui.theme import Theme


# Initialize QApplication for widget tests
app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestContentBrowserItem(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        Theme.apply_mode("light")
        self.content_data = {
            "path": "C:\\test\\book.pdf",
            "type": "pdf",
            "name": "book.pdf",
            "page_count": 150,
            "preview_hash": "abc123"
        }
        self.widget = ContentBrowserItem(self.content_data)

    def tearDown(self):
        """Clean up."""
        self.widget.deleteLater()

    def test_initialization(self):
        """Widget initializes with content data."""
        self.assertEqual(self.widget.file_path, "C:\\test\\book.pdf")
        self.assertEqual(self.widget.content_type, "pdf")

    def test_size_fixed(self):
        """Widget has fixed size."""
        self.assertEqual(self.widget.width(), ContentBrowserItem.ITEM_WIDTH)
        self.assertEqual(self.widget.height(), ContentBrowserItem.ITEM_HEIGHT)

    def test_metadata_formatting_pdf(self):
        """PDF metadata shows page count."""
        metadata_text = self.widget._format_metadata()
        self.assertEqual(metadata_text, "150 pages")

    def test_metadata_formatting_video(self):
        """Video metadata shows duration."""
        video_data = {
            "path": "C:\\test\\video.mp4",
            "type": "video",
            "name": "video.mp4",
            "duration_ms": 125000  # 2:05
        }
        widget = ContentBrowserItem(video_data)
        metadata_text = widget._format_metadata()
        self.assertEqual(metadata_text, "2:05")
        widget.deleteLater()

    def test_clicked_signal(self):
        """Widget emits clicked signal on mouse press."""
        signals_captured = []
        self.widget.clicked.connect(signals_captured.append)

        # Simulate left click
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF

        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(10, 10),
            QPointF(10, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier
        )
        self.widget.mousePressEvent(event)

        self.assertEqual(len(signals_captured), 1)
        self.assertEqual(signals_captured[0], "C:\\test\\book.pdf")

    def test_set_loading_state(self):
        """Widget shows loading placeholder."""
        self.widget.set_loading_state()
        self.assertEqual(self.widget.preview_label.text(), "Loading...")

    def test_set_error_state(self):
        """Widget shows error placeholder."""
        self.widget.set_error_state()
        self.assertIn("unavailable", self.widget.preview_label.text())

    def test_refresh_theme(self):
        """Widget refreshes styling on theme change."""
        Theme.apply_mode("dark")
        self.widget.refresh_theme()
        # Just verify no errors - visual styling is hard to test


class TestContentBrowserGrid(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        Theme.apply_mode("light")
        self.user_data = {}
        self.manager = ContentBrowserManager(self.user_data)

        self.temp_dir = TemporaryDirectory()
        self.preview_dir = Path(self.temp_dir.name) / "previews"
        self.preview_generator = PreviewGenerator(self.preview_dir)

        self.grid = ContentBrowserGrid(self.manager, self.preview_generator)

    def tearDown(self):
        """Clean up."""
        self.grid.deleteLater()
        self.temp_dir.cleanup()

    def test_initialization(self):
        """Grid initializes with manager and preview generator."""
        self.assertIsNotNone(self.grid.content_browser_manager)
        self.assertIsNotNone(self.grid.preview_generator)

    def test_empty_state(self):
        """Grid shows empty state when no content."""
        # Empty state is a centred label outside the flow layout
        self.assertEqual(self.grid.grid_layout.count(), 0)
        self.assertFalse(self.grid.empty_label.isHidden())
        self.assertTrue(self.grid.scroll_area.isHidden())

    def test_content_added_creates_items(self):
        """Adding content creates grid items."""
        self.manager.add_content(
            "C:\\test\\book.pdf",
            "pdf",
            page_count=150
        )

        # Grid should refresh and create item
        self.grid.refresh()

        # Should have one ContentBrowserItem
        self.assertEqual(self.grid.grid_layout.count(), 1)
        widget = self.grid.grid_layout.itemAt(0).widget()
        self.assertIsInstance(widget, ContentBrowserItem)

    def test_content_selected_signal(self):
        """Grid emits content_selected signal when item clicked."""
        self.manager.add_content("C:\\test\\book.pdf", "pdf")
        self.grid.refresh()

        signals_captured = []
        self.grid.content_selected.connect(signals_captured.append)

        # Get the item and click it
        item = self.grid.grid_layout.itemAt(0).widget()
        item.clicked.emit("C:\\test\\book.pdf")

        self.assertEqual(len(signals_captured), 1)
        self.assertEqual(signals_captured[0], "C:\\test\\book.pdf")

    def test_remove_content_refreshes_grid(self):
        """Removing content refreshes the grid."""
        self.manager.add_content("C:\\test\\book.pdf", "pdf")
        self.grid.refresh()
        self.assertEqual(self.grid.grid_layout.count(), 1)

        # Remove content
        self.manager.remove_content("C:\\test\\book.pdf")

        # Grid should auto-refresh and show empty state
        # (via signal connection in _connect_signals)
        self.assertEqual(self.grid.grid_layout.count(), 0)
        self.assertFalse(self.grid.empty_label.isHidden())

    def test_refresh_theme(self):
        """Grid refreshes styling on theme change."""
        self.manager.add_content("C:\\test\\book.pdf", "pdf")
        self.grid.refresh()

        Theme.apply_mode("dark")
        self.grid.refresh_theme()
        # Just verify no errors


if __name__ == "__main__":
    unittest.main()
