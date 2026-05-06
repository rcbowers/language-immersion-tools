"""
Command bar widget for the top of the application.

Provides mode switching, document title, stats, search, and settings access.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QButtonGroup,
)

from immersion_app.gui.theme import Theme


class ModePillGroup(QWidget):
    """Exclusive mode selector pills (PDF/Video)."""

    mode_changed = Signal(str)  # "pdf" or "video"

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Create mode buttons
        self.pdf_button = QPushButton("PDF")
        self.video_button = QPushButton("Video")

        # Make them exclusive
        self.button_group = QButtonGroup(self)
        self.button_group.addButton(self.pdf_button)
        self.button_group.addButton(self.video_button)
        self.pdf_button.setCheckable(True)
        self.video_button.setCheckable(True)
        self.pdf_button.setChecked(True)

        # Connect signals
        self.pdf_button.clicked.connect(lambda: self.mode_changed.emit("pdf"))
        self.video_button.clicked.connect(lambda: self.mode_changed.emit("video"))

        # Apply styling
        self._apply_style()

        layout.addWidget(self.pdf_button)
        layout.addWidget(self.video_button)

    def _apply_style(self):
        """Apply modern pill button styling."""
        style = f"""
            QPushButton {{
                background-color: transparent;
                color: {Theme.TEXT_SOFT};
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12.5px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
            }}
            QPushButton:hover {{
                background-color: {Theme.SURFACE_ALT};
            }}
            QPushButton:checked {{
                background-color: {Theme.ACCENT};
                color: white;
            }}
        """
        self.pdf_button.setStyleSheet(style)
        self.video_button.setStyleSheet(style)

    def set_active_mode(self, mode: str):
        """Set the active mode programmatically."""
        if mode == "pdf":
            self.pdf_button.setChecked(True)
        elif mode == "video":
            self.video_button.setChecked(True)


class TitleWidget(QWidget):
    """Document title and subtitle display."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Title
        self.title_label = QLabel("No document loaded")
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12.5px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
            }}
        """)

        # Subtitle
        self.subtitle_label = QLabel("")
        self.subtitle_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
            }}
        """)

        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)

    def set_title(self, title: str, subtitle: str = ""):
        """Update the title and optional subtitle."""
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))


class StatsChip(QLabel):
    """Stats display chip showing today/total counts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.update_stats(0, 0)
        self._apply_style()

    def _apply_style(self):
        """Apply chip styling."""
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {Theme.ACCENT_SOFT};
                color: {Theme.TEXT};
                border-radius: 6px;
                padding: 4px 10px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
            }}
        """)

    def update_stats(self, today_count: int, total_count: int):
        """Update the stats display."""
        self.setText(f"✨ {today_count} today · {total_count} total")


class CommandBar(QWidget):
    """
    Top command bar with mode switcher, title, stats, search, and settings.
    """

    mode_changed = Signal(str)  # "pdf" or "video"
    search_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(Theme.COMMAND_BAR_HEIGHT)
        self._apply_background()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

        # Left: Mode pills
        self.mode_pills = ModePillGroup()
        self.mode_pills.mode_changed.connect(self.mode_changed.emit)
        layout.addWidget(self.mode_pills)

        # Separator
        layout.addSpacing(8)

        # Title and subtitle
        self.title_widget = TitleWidget()
        layout.addWidget(self.title_widget)

        # Spacer
        layout.addStretch()

        # Stats chip
        self.stats_chip = StatsChip()
        layout.addWidget(self.stats_chip)

        # Search field (stub for now)
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search ⌘K")
        self.search_field.setFixedWidth(180)
        self.search_field.setStyleSheet(Theme.get_input_style())
        self.search_field.returnPressed.connect(self.search_requested.emit)
        layout.addWidget(self.search_field)

        # Settings button
        self.settings_button = QPushButton("⚙")
        self.settings_button.setFixedSize(32, 32)
        self.settings_button.setStyleSheet(Theme.get_button_style("ghost"))
        self.settings_button.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.settings_button)

    def _apply_background(self):
        """Apply command bar background styling."""
        Theme.apply_command_bar_style(self)

    def set_title(self, title: str, subtitle: str = ""):
        """Update the document title."""
        self.title_widget.set_title(title, subtitle)

    def set_stats(self, today_count: int, total_count: int):
        """Update the stats chip."""
        self.stats_chip.update_stats(today_count, total_count)

    def set_mode(self, mode: str):
        """Set the active mode."""
        self.mode_pills.set_active_mode(mode)
