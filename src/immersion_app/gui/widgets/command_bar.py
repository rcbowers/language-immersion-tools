"""
Command bar widget for the top of the application.

Provides recent files access, document title, stats, and settings access.
"""

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QSizePolicy,
)

from immersion_app.gui.theme import Theme


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
    Top command bar with recent files, title, stats, and settings.
    """

    open_requested = Signal()
    close_requested = Signal()
    settings_requested = Signal()
    previous_page_requested = Signal()
    next_page_requested = Signal()
    page_jump_requested = Signal(int)  # 1-based page number
    recent_file_selected = Signal(str, str)  # (file_path, file_type)

    def __init__(self, user_data: dict, parent=None):
        super().__init__(parent)

        self.user_data = user_data
        self._total_pages = 0
        self.setFixedHeight(Theme.COMMAND_BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._apply_background()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Left: Recent files button
        self.recent_button = QPushButton("Recent")
        self.recent_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.recent_button.setFixedHeight(32)
        self.recent_button.clicked.connect(self._show_recent_files_menu)
        layout.addWidget(self.recent_button)

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

    def _show_recent_files_menu(self):
        """Show recent files dropdown menu."""
        from .recent_files_menu import RecentFilesMenu

        menu = RecentFilesMenu(self.user_data, parent=self)
        menu.file_selected.connect(self.recent_file_selected.emit)
        menu.browse_requested.connect(self._trigger_open_dialog)

        # Position menu below the Recent button
        button_geometry = self.recent_button.geometry()
        menu_pos = self.recent_button.mapToGlobal(
            QPoint(0, button_geometry.height())
        )
        menu.exec(menu_pos)

    def _trigger_open_dialog(self):
        """Emit signal to trigger file browser dialog."""
        self.open_requested.emit()
