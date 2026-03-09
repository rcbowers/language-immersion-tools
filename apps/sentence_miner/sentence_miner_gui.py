#!/usr/bin/env python3
"""Sentence miner launcher with mode selection."""

import json
import os
import sys
from pathlib import Path

# Some Windows systems cannot initialize AV1 hardware decode (d3d11) via Qt FFmpeg.
# Force software decoding by default for broader compatibility.
os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "")

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from spanish_sentence_miner import INPUT_FILE

USER_DATA_PATH = Path(INPUT_FILE).resolve().with_name("sentence_miner_user_data.json")


class ModeSelectorDialog(QDialog):
    def __init__(self, has_last_session=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Mode")
        self.resize(420, 220)
        self.selected_mode = None
        self.load_last = False

        layout = QVBoxLayout(self)

        title = QLabel("Select how you want to mine vocabulary")
        layout.addWidget(title)

        row = QHBoxLayout()
        pdf_button = QPushButton("PDF Mode")
        video_button = QPushButton("Video Mode")
        pdf_button.setMinimumHeight(64)
        video_button.setMinimumHeight(64)

        pdf_button.clicked.connect(lambda: self._accept_mode("pdf"))
        video_button.clicked.connect(lambda: self._accept_mode("video"))

        row.addWidget(pdf_button)
        row.addWidget(video_button)
        layout.addLayout(row)

        self.remember_checkbox = QCheckBox("Remember my choice")
        layout.addWidget(self.remember_checkbox)

        if has_last_session:
            load_last_btn = QPushButton("Load Last Session")
            load_last_btn.clicked.connect(self._accept_last_session)
            layout.addWidget(load_last_btn)

        close_row = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        close_row.rejected.connect(self.reject)
        layout.addWidget(close_row)

    def _accept_mode(self, mode):
        self.selected_mode = mode
        self.load_last = False
        self.accept()

    def _accept_last_session(self):
        self.selected_mode = None
        self.load_last = True
        self.accept()

    def remember_choice(self):
        return self.remember_checkbox.isChecked()


def load_user_data():
    default = {
        "mode": "pdf",
        "preferences": {
            "preferred_mode": None,
            "learning_language": "es",
            "native_language": "en",
        },
        "last_session": {
            "pdf_path": "",
            "video_path": "",
        },
    }

    if USER_DATA_PATH.exists():
        try:
            loaded = json.loads(USER_DATA_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                default.update(loaded)
                loaded_preferences = loaded.get("preferences", {})
                if isinstance(loaded_preferences, dict):
                    merged_preferences = dict(default["preferences"])
                    merged_preferences.update(loaded_preferences)
                    default["preferences"] = merged_preferences
                loaded_last = loaded.get("last_session", {})
                if isinstance(loaded_last, dict):
                    merged_last = dict(default["last_session"])
                    merged_last.update(loaded_last)
                    default["last_session"] = merged_last
        except Exception:
            pass
    return default


def save_user_data(payload):
    USER_DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def select_mode(user_data):
    preferred = user_data.get("preferences", {}).get("preferred_mode")
    if preferred in {"pdf", "video"}:
        return preferred

    last = user_data.get("last_session", {})
    has_last_session = bool(last.get("pdf_path") or last.get("video_path"))

    selector = ModeSelectorDialog(has_last_session=has_last_session)
    if selector.exec() != QDialog.DialogCode.Accepted:
        return None

    if selector.load_last:
        mode = user_data.get("mode") or "pdf"
    else:
        mode = selector.selected_mode or "pdf"

    if selector.remember_choice():
        user_data.setdefault("preferences", {})["preferred_mode"] = mode
        save_user_data(user_data)

    return mode


def main():
    app = QApplication(sys.argv)

    user_data = load_user_data()
    mode = select_mode(user_data)
    if mode is None:
        sys.exit(0)

    if mode == "video":
        from video_miner_window import VideoSentenceMinerWindow

        window = VideoSentenceMinerWindow()
    else:
        from pdf_miner_window import PdfSentenceMinerWindow

        window = PdfSentenceMinerWindow()

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
