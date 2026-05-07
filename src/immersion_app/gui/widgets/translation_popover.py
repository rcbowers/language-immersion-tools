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
        # Make this a frameless tool window that floats above native widgets
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # Don't steal focus from the main window
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

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

    def set_anchor_rect(self, rect: QRect):
        """Store the anchor rect for later repositioning."""
        self._anchor_rect = rect

    def reposition_from_stored_anchor(self):
        """Reposition using stored anchor rect (for window resize)."""
        if hasattr(self, '_anchor_rect') and not self._anchor_rect.isNull():
            self.position_near_word(self._anchor_rect)

    def position_near_word(self, word_rect_global: QRect):
        """Place the overlay above the given anchor rect in global screen coordinates."""
        overlay_size = self.sizeHint()
        gap = 10

        # Try to position above the word
        x = word_rect_global.left()
        y = word_rect_global.top() - overlay_size.height() - gap

        # Get screen geometry for bounds checking
        from PySide6.QtWidgets import QApplication
        screen = QApplication.screenAt(word_rect_global.center())
        if screen:
            screen_rect = screen.availableGeometry()

            # Clamp x to screen bounds
            max_x = screen_rect.right() - overlay_size.width()
            x = max(screen_rect.left(), min(x, max_x))

            # If no room above, position below
            if y < screen_rect.top():
                y = word_rect_global.bottom() + gap

            # Ensure y is within screen bounds
            y = max(screen_rect.top(), min(y, screen_rect.bottom() - overlay_size.height()))

        self.setGeometry(x, y, overlay_size.width(), overlay_size.height())

    def show_animated(self):
        """Show the overlay."""
        self.show()
        self.raise_()

    def close(self):
        was_visible = self.isVisible()
        super().close()
        if was_visible:
            self.closed.emit()
