"""
Command bar widget for the top of the application.

Provides mode switching, document title, stats, search, and settings access.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
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
    open_requested = Signal()
    close_requested = Signal()
    search_requested = Signal()
    settings_requested = Signal()
    page_jump_requested = Signal(int)  # 1-based page number

    def __init__(self, parent=None):
        super().__init__(parent)

        self._total_pages = 0
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

        # Open button (always visible)
        self.open_button = QPushButton("Open...")
        self.open_button.setFixedHeight(28)
        self.open_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.open_button.clicked.connect(self.open_requested.emit)
        layout.addWidget(self.open_button)

        layout.addSpacing(8)

        # Title and subtitle
        self.title_widget = TitleWidget()
        layout.addWidget(self.title_widget)

        # Close button (hidden until a file is loaded)
        self.close_button = QPushButton("×")
        self.close_button.setFixedSize(24, 24)
        self.close_button.setStyleSheet(Theme.get_button_style("ghost"))
        self.close_button.setVisible(False)
        self.close_button.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.close_button)

        # Spacer
        layout.addStretch()

        # Page navigation: [current] / [total]
        self.page_current_input = QLineEdit()
        self.page_current_input.setFixedWidth(44)
        self.page_current_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_current_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Theme.SURFACE_ALT};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 5px;
                padding: 3px 6px;
                font-family: {Theme.FONT_MONO};
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.ACCENT_BORDER};
                background-color: {Theme.SURFACE};
            }}
        """)
        self.page_current_input.returnPressed.connect(self._on_page_input_committed)
        self.page_current_input.setVisible(False)

        self.page_separator = QLabel("/")
        self.page_separator.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_MONO};
                font-size: 12px;
                padding: 0 2px;
            }}
        """)
        self.page_separator.setVisible(False)

        self.page_total_label = QLabel("0")
        self.page_total_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_MONO};
                font-size: 12px;
            }}
        """)
        self.page_total_label.setVisible(False)

        layout.addWidget(self.page_current_input)
        layout.addWidget(self.page_separator)
        layout.addWidget(self.page_total_label)
        layout.addSpacing(8)

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

    def set_file_loaded(self, loaded: bool):
        """Show or hide the close button based on whether a file is loaded."""
        self.close_button.setVisible(loaded)

    def set_page_info(self, current: int, total: int):
        """Show/update page counter. Pass total=0 to hide."""
        visible = total > 0
        self.page_current_input.setVisible(visible)
        self.page_separator.setVisible(visible)
        self.page_total_label.setVisible(visible)
        if visible:
            self._total_pages = total
            self.page_current_input.setValidator(QIntValidator(1, total, self))
            self.page_current_input.setText(str(current))
            self.page_total_label.setText(str(total))

    def _on_page_input_committed(self):
        text = self.page_current_input.text().strip()
        if not text.isdigit():
            return
        page = max(1, min(int(text), self._total_pages))
        self.page_current_input.clearFocus()
        self.page_jump_requested.emit(page)
