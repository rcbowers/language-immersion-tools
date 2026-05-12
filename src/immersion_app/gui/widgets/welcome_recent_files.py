"""Welcome screen recent files list widget."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QCursor

from ...core.recent_files import get_recent_files, format_time_ago, format_position_metadata
from ..theme import Theme


class WelcomeRecentFileItem(QWidget):
    """Single recent file row for welcome screen."""
    clicked = Signal(str, str)  # (file_path, file_type)

    def __init__(self, file_data: dict):
        super().__init__()
        self.file_data = file_data
        self.file_path = file_data.get("path", "")
        self.file_type = file_data.get("type", "")
        self._setup_ui()

    def _setup_ui(self):
        """Set up the item UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # Icon + Filename row
        icon = "📄" if self.file_type == "pdf" else "🎬"
        filename = self.file_data.get("name", "Unknown")

        self.filename_label = QLabel(f"{icon}  {filename}")
        self.filename_label.setWordWrap(False)
        self.filename_label.setTextFormat(Qt.PlainText)

        # Metadata row (position + time)
        page_index = self.file_data.get("page_index", 0)
        video_position_ms = self.file_data.get("video_position_ms", 0)
        position_text = format_position_metadata(self.file_type, page_index, video_position_ms)

        timestamp_iso = self.file_data.get("last_opened", "")
        time_text = format_time_ago(timestamp_iso)

        metadata_text = f"{position_text} · {time_text}"

        self.metadata_label = QLabel(metadata_text)

        layout.addWidget(self.filename_label)
        layout.addWidget(self.metadata_label)

        self.setFixedHeight(64)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        # Set base style
        self.refresh_theme()

    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.file_path, self.file_type)

    def refresh_theme(self):
        self.filename_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 15px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
            }}
        """)
        self.metadata_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12px;
            }}
        """)
        self.setStyleSheet(f"""
            WelcomeRecentFileItem {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER};
                border-radius: 8px;
            }}
            WelcomeRecentFileItem:hover {{
                background-color: {Theme.SURFACE_ALT};
                border-color: {Theme.ACCENT};
            }}
        """)


class WelcomeRecentFilesList(QWidget):
    """Recent files list for welcome screen."""
    file_selected = Signal(str, str)  # (file_path, file_type)

    def __init__(self, user_data: dict):
        super().__init__()
        self.user_data = user_data
        self._setup_ui()

    def _setup_ui(self):
        """Set up the list UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create scroll area for list
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setMinimumHeight(150)
        self.scroll_area.setMaximumHeight(350)

        # Container for list items
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)

        self.scroll_area.setWidget(self.list_container)
        main_layout.addWidget(self.scroll_area)

        # Populate list
        self.refresh()
        self.refresh_theme()

    def refresh(self):
        """Refresh the list of recent files."""
        # Clear existing items
        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Get recent files
        recent_files = get_recent_files(self.user_data, validate_exists=True)

        if recent_files:
            # Add each recent file
            for file_data in recent_files:
                item = WelcomeRecentFileItem(file_data)
                item.clicked.connect(self.file_selected.emit)
                self.list_layout.addWidget(item)

            # Add stretch at the bottom
            self.list_layout.addStretch()
        else:
            # Show empty state
            empty_label = QLabel("No recent files yet\nOpen a PDF or video to get started")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"""
                QLabel {{
                    color: {Theme.TEXT_MUTED};
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: 13px;
                    line-height: 1.5;
                    padding: 40px 20px;
                }}
            """)
            self.list_layout.addWidget(empty_label)

    def refresh_theme(self):
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            {Theme.get_scrollbar_style()}
        """)
        for index in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(index).widget()
            if widget and hasattr(widget, "refresh_theme"):
                widget.refresh_theme()
