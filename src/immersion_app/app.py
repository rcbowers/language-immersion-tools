"""Application entrypoint for the unified workspace."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase

from immersion_app.core.logging_config import setup_logging
from immersion_app.gui.main_window import UnifiedSentenceMinerWindow


os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "")


class ConsoleCapture(QObject):
    text_emitted = Signal(str)

    def __init__(self):
        super().__init__()
        self._buffer: list[str] = []
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self._excepthook = sys.excepthook

    def install(self):
        sys.stdout = _ConsoleStream(self, self._stdout)
        sys.stderr = _ConsoleStream(self, self._stderr)
        sys.excepthook = self._handle_exception

    def restore(self):
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        sys.excepthook = self._excepthook

    def replay(self):
        for chunk in self._buffer:
            self.text_emitted.emit(chunk)

    def write(self, text: str):
        if not text:
            return
        self._buffer.append(text)
        self.text_emitted.emit(text)

    def _handle_exception(self, exc_type, exc_value, exc_traceback):
        self.write("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        if self._excepthook:
            self._excepthook(exc_type, exc_value, exc_traceback)


class _ConsoleStream:
    def __init__(self, capture: ConsoleCapture, fallback):
        self.capture = capture
        self.fallback = fallback

    def write(self, text):
        if not isinstance(text, str):
            text = str(text)
        self.capture.write(text)
        if self.fallback and self.fallback not in (sys.stdout, sys.stderr):
            try:
                self.fallback.write(text)
            except Exception:
                pass
        return len(text)

    def flush(self):
        if self.fallback and self.fallback not in (sys.stdout, sys.stderr):
            try:
                self.fallback.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def main():
    app = QApplication(sys.argv)
    console_capture = ConsoleCapture()
    console_capture.install()

    # Setup logging system with dual output (file + UI console)
    log_file = setup_logging(console_capture)

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

    window = UnifiedSentenceMinerWindow(console_capture=console_capture)
    window.showMaximized()
    window.connect_console_capture()
    console_capture.replay()
    try:
        return app.exec()
    finally:
        console_capture.restore()


if __name__ == "__main__":
    raise SystemExit(main())
