#!/usr/bin/env python3
"""Clickable subtitle overlay widget."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel


class ClickableSubtitleLabel(QLabel):
    clicked = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._raw_text = ""
        self._highlighted_word = ""
        self._words = []

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(
            "QLabel {"
            "color: white;"
            "background-color: rgba(0, 0, 0, 150);"
            "padding: 10px;"
            "border-radius: 6px;"
            "font-size: 20px;"
            "font-weight: 700;"
            "}"
        )

    def set_subtitle_text(self, text):
        self._raw_text = text or ""
        self._highlighted_word = ""
        self._words = [w for w in self._raw_text.split() if w]
        self.setText(self._raw_text)

    def highlight_word(self, word):
        self._highlighted_word = word or ""
        if not self._raw_text or not self._highlighted_word:
            self.setText(self._raw_text)
            return

        highlighted = []
        target = self._highlighted_word.lower()
        for token in self._raw_text.split():
            clean = "".join(c for c in token if c.isalnum() or c == "_").lower()
            if clean == target:
                highlighted.append(f"<span style='background-color: yellow; color: black;'>{token}</span>")
            else:
                highlighted.append(token)
        self.setText(" ".join(highlighted))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._words:
            super().mousePressEvent(event)
            return

        word = self._word_at_position(event.position().x())
        if word:
            self.clicked.emit(word, event.modifiers())
        super().mousePressEvent(event)

    def _word_at_position(self, x_pos):
        metrics = QFontMetrics(self.font())
        text = self._raw_text
        total_width = metrics.horizontalAdvance(text)
        left = (self.width() - total_width) / 2
        if x_pos < left:
            return None

        cursor = left
        for token in text.split():
            token_width = metrics.horizontalAdvance(token)
            if cursor <= x_pos <= cursor + token_width:
                return token
            cursor += token_width + metrics.horizontalAdvance(" ")
        return None
