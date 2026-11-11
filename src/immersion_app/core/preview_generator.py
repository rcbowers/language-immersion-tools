"""Preview generation service for content browser."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pymupdf
from PySide6.QtCore import QObject, QRunnable, Signal

from immersion_app.core.pdf_service import EPUB_FONT_SIZE, EPUB_PAGE_HEIGHT, EPUB_PAGE_WIDTH
from immersion_app.core.signals import safe_emit

logger = logging.getLogger(__name__)


class PreviewGenerationSignals(QObject):
    """Signals for preview generation tasks."""
    finished = Signal(str, str)  # (file_path, preview_path)
    failed = Signal(str, str)  # (file_path, error_message)


class PreviewGenerationTask(QRunnable):
    """Background task for generating preview thumbnails."""

    PREVIEW_WIDTH = 300
    PREVIEW_HEIGHT = 400

    def __init__(self, file_path: str, content_type: str, preview_hash: str, preview_dir: Path):
        super().__init__()
        self.file_path = file_path
        self.content_type = content_type
        self.preview_hash = preview_hash
        self.preview_dir = preview_dir
        self.signals = PreviewGenerationSignals()

    def run(self):
        """Generate preview thumbnail (runs on background thread)."""
        try:
            preview_path = self._generate_preview()
        except Exception as exc:
            logger.error(
                "Preview generation failed for %s: %s",
                self.file_path,
                exc,
                exc_info=True
            )
            safe_emit(self.signals.failed, self.file_path, str(exc))
            return
        safe_emit(self.signals.finished, self.file_path, preview_path)

    def _generate_preview(self) -> str:
        """Generate preview and return path to cached file."""
        preview_filename = f"{self.preview_hash}_{self.content_type}.jpg"
        preview_path = self.preview_dir / preview_filename

        # Ensure preview directory exists
        self.preview_dir.mkdir(parents=True, exist_ok=True)

        if self.content_type in ("pdf", "epub"):
            self._generate_pdf_preview(preview_path)
        elif self.content_type == "video":
            self._generate_video_preview(preview_path)
        else:
            raise ValueError(f"Unknown content type: {self.content_type}")

        return str(preview_path)

    def _generate_pdf_preview(self, preview_path: Path) -> None:
        """Generate a first-page preview for a PDF or EPUB using PyMuPDF."""
        doc = pymupdf.open(self.file_path)
        try:
            if doc.is_reflowable:
                doc.layout(width=EPUB_PAGE_WIDTH, height=EPUB_PAGE_HEIGHT, fontsize=EPUB_FONT_SIZE)
            # Render first page
            page = doc.load_page(0)

            # Calculate zoom to fit target dimensions
            page_rect = page.rect
            zoom_x = self.PREVIEW_WIDTH / page_rect.width
            zoom_y = self.PREVIEW_HEIGHT / page_rect.height
            zoom = min(zoom_x, zoom_y)

            matrix = pymupdf.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            # Save as JPEG
            pix.save(str(preview_path), "jpeg")
        finally:
            doc.close()

    def _generate_video_preview(self, preview_path: Path) -> None:
        """Generate video preview using ffmpeg."""
        try:
            import ffmpeg
        except ImportError:
            raise ImportError("ffmpeg-python is required for video preview generation")

        # Extract frame at 1 second
        try:
            (
                ffmpeg
                .input(self.file_path, ss=1)
                .filter('scale', self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT, force_original_aspect_ratio='decrease')
                .output(str(preview_path), vframes=1, format='image2', vcodec='mjpeg')
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True, quiet=True)
            )
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
            raise RuntimeError(f"FFmpeg error: {error_msg}")


class PreviewGenerator(QObject):
    """
    Service for generating and managing preview thumbnails.

    Generates thumbnails asynchronously and caches them on disk.
    """

    preview_generated = Signal(str, str)  # (file_path, preview_path)
    preview_failed = Signal(str, str)  # (file_path, error_message)

    def __init__(self, preview_dir: str | Path, parent: QObject | None = None):
        super().__init__(parent)
        self.preview_dir = Path(preview_dir)

    def get_cached_preview(self, preview_hash: str, content_type: str) -> str | None:
        """
        Get cached preview path if it exists.

        Returns:
            Path to cached preview, or None if not cached
        """
        preview_filename = f"{preview_hash}_{content_type}.jpg"
        preview_path = self.preview_dir / preview_filename

        if preview_path.exists():
            return str(preview_path)
        return None

    def generate_preview(
        self,
        file_path: str,
        content_type: str,
        preview_hash: str,
        thread_pool
    ) -> None:
        """
        Generate preview asynchronously.

        Emits preview_generated or preview_failed signal when complete.
        """
        # Check if file exists
        if not os.path.exists(file_path):
            self.preview_failed.emit(file_path, "File not found")
            return

        # Create and start background task
        task = PreviewGenerationTask(file_path, content_type, preview_hash, self.preview_dir)
        task.signals.finished.connect(self._on_preview_finished)
        task.signals.failed.connect(self._on_preview_failed)
        thread_pool.start(task)

    def _on_preview_finished(self, file_path: str, preview_path: str):
        """Forward preview generation success signal."""
        self.preview_generated.emit(file_path, preview_path)

    def _on_preview_failed(self, file_path: str, error_message: str):
        """Forward preview generation failure signal."""
        self.preview_failed.emit(file_path, error_message)
