"""Application entrypoint for the unified workspace."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from immersion_app.core.logging_config import setup_logging
from immersion_app.gui.main_window import UnifiedSentenceMinerWindow


os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "")


def main():
    app = QApplication(sys.argv)

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

    window = UnifiedSentenceMinerWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
