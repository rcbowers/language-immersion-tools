"""Application entrypoint for the unified workspace."""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from immersion_app.gui.main_window import UnifiedSentenceMinerWindow


os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "")


def main():
    app = QApplication(sys.argv)
    window = UnifiedSentenceMinerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
