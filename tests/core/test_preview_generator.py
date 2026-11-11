"""Tests for PreviewGenerator."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QThreadPool

from immersion_app.core.preview_generator import PreviewGenerator, PreviewGenerationTask


class TestPreviewGenerator(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = TemporaryDirectory()
        self.preview_dir = Path(self.temp_dir.name) / "previews"
        self.generator = PreviewGenerator(self.preview_dir)

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_initialization(self):
        """Generator initializes with preview directory."""
        self.assertEqual(self.generator.preview_dir, self.preview_dir)

    def test_get_cached_preview_exists(self):
        """Returns cached preview path if file exists."""
        # Create a fake preview file
        self.preview_dir.mkdir(parents=True)
        preview_file = self.preview_dir / "abc123_pdf.jpg"
        preview_file.touch()

        result = self.generator.get_cached_preview("abc123", "pdf")
        self.assertEqual(result, str(preview_file))

    def test_get_cached_preview_not_exists(self):
        """Returns None if preview file doesn't exist."""
        result = self.generator.get_cached_preview("abc123", "pdf")
        self.assertIsNone(result)

    def test_generate_preview_file_not_found(self):
        """Emits preview_failed signal when file doesn't exist."""
        signals_captured = []

        def capture_failed(file_path, error_msg):
            signals_captured.append((file_path, error_msg))

        self.generator.preview_failed.connect(capture_failed)

        thread_pool = QThreadPool()
        self.generator.generate_preview(
            "C:\\nonexistent\\file.pdf",
            "pdf",
            "abc123",
            thread_pool
        )

        # Should emit failed signal immediately
        self.assertEqual(len(signals_captured), 1)
        self.assertIn("C:\\nonexistent\\file.pdf", signals_captured[0][0])

    def test_epub_preview_renders_first_page(self):
        """EPUB previews are laid out and rendered like a PDF first page."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from epub_helpers import build_epub

        self.preview_dir.mkdir(parents=True)
        epub = build_epub(Path(self.temp_dir.name) / "libro.epub", chapters=1, paragraphs=5)
        task = PreviewGenerationTask(str(epub), "epub", "ep123", self.preview_dir)
        finished = []
        task.signals.finished.connect(lambda fp, pp: finished.append(pp))

        task.run()

        self.assertEqual(len(finished), 1)
        self.assertTrue(finished[0].endswith("ep123_epub.jpg"))
        self.assertGreater(Path(finished[0]).stat().st_size, 0)

    @patch('immersion_app.core.preview_generator.pymupdf')
    def test_pdf_preview_generation_task(self, mock_fitz):
        """PDF preview generation task creates thumbnail."""
        # Create preview directory
        self.preview_dir.mkdir(parents=True)

        # Mock PDF document
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_pixmap = MagicMock()

        mock_fitz.open.return_value = mock_doc
        mock_doc.load_page.return_value = mock_page
        mock_page.get_pixmap.return_value = mock_pixmap
        mock_page.rect.width = 600
        mock_page.rect.height = 800

        # Create test PDF file (empty is fine for this test)
        test_pdf = Path(self.temp_dir.name) / "test.pdf"
        test_pdf.touch()

        # Create and run task
        task = PreviewGenerationTask(
            str(test_pdf),
            "pdf",
            "test123",
            self.preview_dir
        )

        signals_captured = []
        task.signals.finished.connect(lambda fp, pp: signals_captured.append((fp, pp)))

        task.run()

        # Should emit finished signal
        self.assertEqual(len(signals_captured), 1)
        file_path, preview_path = signals_captured[0]
        self.assertEqual(file_path, str(test_pdf))
        self.assertIn("test123_pdf.jpg", preview_path)

        # Should have called PyMuPDF
        mock_fitz.open.assert_called_once_with(str(test_pdf))
        mock_pixmap.save.assert_called_once()

    def test_preview_generation_unknown_type(self):
        """Task fails with unknown content type."""
        # Create test file
        test_file = Path(self.temp_dir.name) / "test.unknown"
        test_file.touch()

        task = PreviewGenerationTask(
            str(test_file),
            "unknown_type",
            "test123",
            self.preview_dir
        )

        signals_captured = []
        task.signals.failed.connect(lambda fp, err: signals_captured.append((fp, err)))

        task.run()

        # Should emit failed signal
        self.assertEqual(len(signals_captured), 1)
        self.assertIn("Unknown content type", signals_captured[0][1])


if __name__ == "__main__":
    unittest.main()
