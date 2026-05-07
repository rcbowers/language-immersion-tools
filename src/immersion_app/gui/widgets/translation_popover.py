"""Inline translation overlay widget."""

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from immersion_app.gui.theme import Theme


class TranslationPopover(QWidget):
    """Compact inline overlay anchored above a selected word or phrase."""

    add_requested = Signal()
    edit_requested = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(f"""
            TranslationPopover {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER_STRONG};
                border-radius: 10px;
            }}
        """)
        self.hide()
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self.translation_label = QLabel("")
        self.translation_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.ACCENT_DARK};
                background: transparent;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
            }}
        """)
        layout.addWidget(self.translation_label)

        self.add_button = QPushButton("+")
        self.add_button.setFixedSize(26, 26)
        self.add_button.setStyleSheet(Theme.get_button_style("compact_accent"))
        self.add_button.clicked.connect(self.add_requested.emit)
        layout.addWidget(self.add_button)

        self.edit_button = QPushButton("Edit")
        self.edit_button.setFixedHeight(26)
        self.edit_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.edit_button.clicked.connect(self.edit_requested.emit)
        layout.addWidget(self.edit_button)

    def set_content(
        self,
        word: str,
        meaning: str,
        sentence: str = "",
        sentence_translation: str = "",
        metadata: str = "",
    ):
        """Update the inline overlay text."""
        self.translation_label.setText(meaning)
        self.translation_label.setToolTip(word)
        self.adjustSize()

    def position_near_word(self, word_rect: QRect):
        """Place the overlay above the given anchor rect in parent coordinates."""
        if self.parentWidget() is None:
            return

        parent_rect = self.parentWidget().rect()
        overlay_size = self.sizeHint()
        gap = 10
        x = word_rect.left()
        y = word_rect.top() - overlay_size.height() - gap

        max_x = max(0, parent_rect.width() - overlay_size.width())
        x = max(0, min(x, max_x))

        if y < 0:
            y = min(parent_rect.height() - overlay_size.height(), word_rect.bottom() + gap)
        else:
            y = min(y, parent_rect.height() - overlay_size.height())

        self.setGeometry(x, max(0, y), overlay_size.width(), overlay_size.height())

    def show_animated(self):
        """Show the overlay."""
        self.show()
        self.raise_()

    def close(self):
        was_visible = self.isVisible()
        super().close()
        if was_visible:
            self.closed.emit()
