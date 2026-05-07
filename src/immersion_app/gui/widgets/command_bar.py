"""
Command bar widget for the top of the application.

Provides mode switching, document title, stats, and settings access.
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
        self.setText(f"âœ¨ {today_count} today Â· {total_count} total")


class CommandBar(QWidget):
    """
    Top command bar with mode switcher, title, stats, and settings.
    """

    mode_changed = Signal(str)  # "pdf" or "video"
    open_requested = Signal()
    close_requested = Signal()
    settings_requested = Signal()
    previous_page_requested = Signal()
    next_page_requested = Signal()
    page_jump_requested = Signal(int)  # 1-based page number

    def __init__(self, parent=None):
        super().__init__(parent)

        self._total_pages = 0
        self.setFixedHeight(Theme.COMMAND_BAR_HEIGHT)
        self._apply_background()
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Left: Mode pills
        self.mode_pills = ModePillGroup()
        self.mode_pills.mode_changed.connect(self.mode_changed.emit)
        layout.addWidget(self.mode_pills)

        # Separator
        layout.addSpacing(8)

        # Open button (always visible)
        self.open_button = QPushButton("Open...")
        self.open_button.setFixedHeight(32)
        self.open_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.open_button.clicked.connect(self.open_requested.emit)
        layout.addWidget(self.open_button)

        layout.addSpacing(8)

        # Title and subtitle
        self.title_widget = TitleWidget()
        layout.addWidget(self.title_widget)

        # Close button (hidden until a file is loaded)
        self.close_button = QPushButton("Ã—")
        self.close_button.setFixedSize(24, 24)
        self.close_button.setStyleSheet(Theme.get_button_style("ghost"))
        self.close_button.setVisible(False)
        self.close_button.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.close_button)

        # Spacer
        layout.addStretch()

        # Page navigation: [<] [current] [>]
        self.page_prev_button = QPushButton("<")
        self.page_prev_button.setFixedSize(28, 28)
        self.page_prev_button.setStyleSheet(Theme.get_button_style("ghost"))
        self.page_prev_button.clicked.connect(self.previous_page_requested.emit)
        self.page_prev_button.setVisible(False)

        self.page_current_input = QLineEdit()
        self.page_current_input.setFixedWidth(44)
        self.page_current_input.setFixedHeight(28)
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

        self.page_next_button = QPushButton(">")
        self.page_next_button.setFixedSize(28, 28)
        self.page_next_button.setStyleSheet(Theme.get_button_style("ghost"))
        self.page_next_button.clicked.connect(self.next_page_requested.emit)
        self.page_next_button.setVisible(False)

        layout.addWidget(self.page_prev_button)
        layout.addWidget(self.page_current_input)
        layout.addWidget(self.page_next_button)
        layout.addSpacing(8)

        # Stats chip
        self.stats_chip = StatsChip()
        layout.addWidget(self.stats_chip)

        # Settings button
        self.settings_button = QPushButton("âš™")
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
        """Show/update PDF page controls. Pass total=0 to hide."""
        visible = total > 0
        self.page_prev_button.setVisible(visible)
        self.page_current_input.setVisible(visible)
        self.page_next_button.setVisible(visible)
        self._total_pages = total
        if visible:
            self.page_current_input.setValidator(QIntValidator(1, total, self))
            self.page_current_input.setText(str(current))
            self.page_prev_button.setEnabled(current > 1)
            self.page_next_button.setEnabled(current < total)
        else:
            self.page_current_input.clear()

    def _on_page_input_committed(self):
        text = self.page_current_input.text().strip()
        if not text.isdigit() or self._total_pages <= 0:
            return
        page = max(1, min(int(text), self._total_pages))
        self.page_current_input.setText(str(page))
        self.page_current_input.clearFocus()
        self.page_jump_requested.emit(page)
