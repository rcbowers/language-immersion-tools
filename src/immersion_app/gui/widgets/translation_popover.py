"""
Translation popover widget - floating card for word translations.

Displays word translation information in a modern popover that appears
near the clicked word.
"""

from PySide6.QtCore import Qt, Signal, QRect, QPropertyAnimation, QPoint
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QApplication,
    QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QScreen, QColor

from immersion_app.gui.theme import Theme


class TranslationPopover(QWidget):
    """
    Floating popover widget that shows translation information.

    Appears near clicked words with translation, context, and action buttons.
    """

    add_requested = Signal()
    edit_requested = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Frameless popup window
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Fixed width, height fits content
        self.setFixedWidth(Theme.POPOVER_WIDTH)

        # Build UI
        self._build_ui()

        # Animation for fade-in
        self.opacity_animation = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_animation.setDuration(150)
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)

    def _build_ui(self):
        """Build the popover UI structure."""
        # Main container
        container = QWidget(self)
        container.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER};
                border-radius: 12px;
            }}
        """)

        # Add drop shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 40))
        container.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header section
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(14, 16, 14, 10)
        header_layout.setSpacing(4)

        # Headword and close button row
        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self.headword_label = QLabel("Word")
        self.headword_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: {Theme.FONT_SIZE_HEADING};
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
            }}
        """)
        title_row.addWidget(self.headword_label)
        title_row.addStretch()

        # Close button
        close_button = QPushButton("✕")
        close_button.setFixedSize(24, 24)
        close_button.setStyleSheet(Theme.get_button_style("ghost"))
        close_button.clicked.connect(self.close)
        title_row.addWidget(close_button)

        header_layout.addLayout(title_row)

        # POS and IPA (second line)
        self.metadata_label = QLabel("")
        self.metadata_label.setStyleSheet(Theme.get_label_style("caption"))
        header_layout.addWidget(self.metadata_label)

        main_layout.addWidget(header_widget)

        # Meaning section
        meaning_widget = QWidget()
        meaning_layout = QVBoxLayout(meaning_widget)
        meaning_layout.setContentsMargins(0, 16, 0, 16)
        meaning_layout.setSpacing(8)

        self.meaning_label = QLabel("")
        self.meaning_label.setWordWrap(True)
        self.meaning_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
                padding: 0px 16px;
            }}
        """)
        meaning_layout.addWidget(self.meaning_label)

        main_layout.addWidget(meaning_widget)

        # Context block
        context_widget = QWidget()
        context_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.SURFACE_ALT};
                border-radius: 0px;
            }}
        """)
        context_layout = QVBoxLayout(context_widget)
        context_layout.setContentsMargins(16, 10, 16, 10)
        context_layout.setSpacing(6)

        # "IN CONTEXT" eyebrow
        eyebrow = QLabel("IN CONTEXT")
        eyebrow.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 10px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
                letter-spacing: 0.5px;
            }}
        """)
        context_layout.addWidget(eyebrow)

        # Source sentence
        self.sentence_label = QLabel("")
        self.sentence_label.setWordWrap(True)
        self.sentence_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
            }}
        """)
        context_layout.addWidget(self.sentence_label)

        # English translation
        self.context_translation_label = QLabel("")
        self.context_translation_label.setWordWrap(True)
        self.context_translation_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_SOFT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
            }}
        """)
        context_layout.addWidget(self.context_translation_label)

        main_layout.addWidget(context_widget)

        # Actions section
        actions_widget = QWidget()
        actions_layout = QVBoxLayout(actions_widget)
        actions_layout.setContentsMargins(16, 10, 16, 16)
        actions_layout.setSpacing(8)

        # Add to Anki button (primary)
        self.add_button = QPushButton("+ Add to Anki ⏎")
        self.add_button.setStyleSheet(Theme.get_button_style("primary"))
        self.add_button.clicked.connect(self.add_requested.emit)
        actions_layout.addWidget(self.add_button)

        # Edit button (secondary)
        self.edit_button = QPushButton("✎ Edit")
        self.edit_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.edit_button.clicked.connect(self.edit_requested.emit)
        actions_layout.addWidget(self.edit_button)

        main_layout.addWidget(actions_widget)

        # Set container as main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container)

    def set_content(
        self,
        word: str,
        meaning: str,
        sentence: str = "",
        sentence_translation: str = "",
        metadata: str = "",
    ):
        """
        Set the popover content.

        Args:
            word: The headword to display
            meaning: Word translation/definition
            sentence: Source language sentence (context)
            sentence_translation: Translation of the sentence
            metadata: Part of speech, IPA, etc.
        """
        self.headword_label.setText(word)
        self.meaning_label.setText(meaning)
        self.sentence_label.setText(sentence)
        self.context_translation_label.setText(sentence_translation)
        self.metadata_label.setText(metadata)
        self.metadata_label.setVisible(bool(metadata))

        # Adjust height to fit content
        self.adjustSize()

    def position_near_word(self, word_global_rect: QRect):
        """
        Position the popover near the clicked word.

        Tries to show below the word with 8px gap, but flips above if
        there's not enough space. Ensures 8px margin from screen edges.

        Args:
            word_global_rect: Global screen coordinates of the clicked word
        """
        # Get the screen containing the word
        screen = QApplication.screenAt(word_global_rect.center())
        if not screen:
            screen = QApplication.primaryScreen()

        screen_geometry = screen.availableGeometry()

        # Calculate popover dimensions
        popover_width = self.width()
        popover_height = self.sizeHint().height()

        # Try to center horizontally relative to the word
        x = word_global_rect.center().x() - popover_width // 2

        # Ensure horizontal margins
        margin = 8
        if x < screen_geometry.left() + margin:
            x = screen_geometry.left() + margin
        elif x + popover_width > screen_geometry.right() - margin:
            x = screen_geometry.right() - margin - popover_width

        # Vertical positioning: prefer below, flip above if needed
        gap = 8
        y_below = word_global_rect.bottom() + gap
        y_above = word_global_rect.top() - gap - popover_height

        # Check available space below vs above
        space_below = screen_geometry.bottom() - y_below
        space_above = word_global_rect.top() - screen_geometry.top()

        if space_below >= popover_height or space_below >= space_above:
            # Show below
            y = y_below
        else:
            # Show above
            y = y_above

        # Ensure vertical margins
        if y < screen_geometry.top() + margin:
            y = screen_geometry.top() + margin
        elif y + popover_height > screen_geometry.bottom() - margin:
            y = screen_geometry.bottom() - margin - popover_height

        # Set position
        self.move(x, y)

    def show_animated(self):
        """Show the popover with fade-in animation."""
        self.show()
        self.opacity_animation.start()

    def closeEvent(self, event):
        """Handle close event."""
        self.closed.emit()
        super().closeEvent(event)
