"""Application entrypoint for the unified workspace."""

from __future__ import annotations

import os
import sys

# Must be set before any Qt or PySide6 imports so the multimedia plugin
# loader picks up the FFmpeg backend (supports AV1, HEVC, etc.)
os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"
os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "")

from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from immersion_app.core.logging_config import setup_logging
from immersion_app.core.paths import ensure_runtime_dirs, migrate_legacy_data
from immersion_app.gui.main_window import UnifiedSentenceMinerWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LinguaLoop")

    # Move pre-1.0 ``<repo>/data`` into the per-user data folder (once).
    migrated = migrate_legacy_data()
    ensure_runtime_dirs()

    # Setup logging system with dual output (file + terminal)
    setup_logging()

    # Load Inter font family
    font_dir = Path(__file__).parent / "gui" / "fonts"
    font_files = [
        "Inter-Regular.ttf",
        "Inter-Medium.ttf",
        "Inter-SemiBold.ttf",
        "Inter-Bold.ttf"
    ]
    for font_file in font_files:
        font_path = font_dir / font_file
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))

    if migrated:
        import logging
        logging.getLogger(__name__).info("Legacy ./data folder copied to the per-user data folder")

    window = UnifiedSentenceMinerWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
