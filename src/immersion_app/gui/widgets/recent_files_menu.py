"""Recent files dropdown menu widget."""

from PySide6.QtWidgets import QMenu, QWidgetAction, QWidget, QVBoxLayout, QLabel, QFileDialog
from PySide6.QtCore import Signal, Qt, QPoint
from PySide6.QtGui import QCursor

from ...core.recent_files import get_recent_files, format_time_ago, format_position_metadata
from ..theme import Theme


class RecentFileMenuItem(QWidget):
    """Custom widget for a single recent file menu item."""
    clicked = Signal(str, str)  # (file_path, file_type)

    def __init__(self, file_data: dict):
        super().__init__()
        self.file_data = file_data
        self.file_path = file_data.get("path", "")
        self.file_type = file_data.get("type", "")
        self._setup_ui()

    def _setup_ui(self):
        """Set up the menu item UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # Icon + Filename row
        icon = "📄" if self.file_type == "pdf" else "🎬"
        filename = self.file_data.get("name", "Unknown")

        filename_label = QLabel(f"{icon} {filename}")
        filename_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 14px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
            }}
        """)
        filename_label.setWordWrap(False)
        # Enable text elision
        filename_label.setTextFormat(Qt.PlainText)
        filename_label.setMaximumWidth(350)

        # Metadata row (position + time)
        page_index = self.file_data.get("page_index", 0)
        video_position_ms = self.file_data.get("video_position_ms", 0)
        position_text = format_position_metadata(self.file_type, page_index, video_position_ms)

        timestamp_iso = self.file_data.get("last_opened", "")
        time_text = format_time_ago(timestamp_iso)

        metadata_text = f"{position_text} · {time_text}"

        metadata_label = QLabel(metadata_text)
        metadata_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
            }}
        """)

        layout.addWidget(filename_label)
        layout.addWidget(metadata_label)

        self.setFixedHeight(56)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        # Set base style
        self.setStyleSheet(f"""
            RecentFileMenuItem {{
                background-color: transparent;
                border-radius: 4px;
            }}
            RecentFileMenuItem:hover {{
                background-color: {Theme.SURFACE_ALT};
            }}
        """)

    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.file_path, self.file_type)
            # Close the parent menu
            menu = self.window()
            if isinstance(menu, QMenu):
                menu.close()


class RecentFilesMenu(QMenu):
    """Dropdown menu showing recent files."""
    file_selected = Signal(str, str)  # (file_path, file_type)
    browse_requested = Signal()  # Signal to open file browser

    def __init__(self, user_data: dict, parent=None):
        super().__init__(parent)
        self.user_data = user_data
        self._setup_ui()

    def _setup_ui(self):
        """Set up the menu UI."""
        # Get recent files
        recent_files = get_recent_files(self.user_data, validate_exists=True)

        if recent_files:
            # Add each recent file as a custom widget action
            for file_data in recent_files:
                item = RecentFileMenuItem(file_data)
                item.clicked.connect(self.file_selected.emit)

                action = QWidgetAction(self)
                action.setDefaultWidget(item)
                self.addAction(action)

            # Add separator before browse action
            self.addSeparator()
        else:
            # Show empty state
            empty_action = self.addAction("No recent files")
            empty_action.setEnabled(False)
            self.addSeparator()

        # Add "Browse for file..." action at bottom
        browse_action = self.addAction("Browse for file...")
        browse_action.triggered.connect(self.browse_requested.emit)

        # Style the menu
        self.setStyleSheet(f"""
            QMenu {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                color: {Theme.TEXT};
                padding: 8px 12px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {Theme.SURFACE_ALT};
            }}
            QMenu::item:disabled {{
                color: {Theme.TEXT_MUTED};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {Theme.BORDER};
                margin: 4px 0px;
            }}
        """)

        # Set minimum width
        self.setMinimumWidth(300)
