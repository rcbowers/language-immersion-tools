"""Content browser grid item widget."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QCursor, QPixmap, QContextMenuEvent
from PySide6.QtWidgets import QMenu

from ..theme import Theme


class ContentBrowserItem(QWidget):
    """Single content item card for content browser grid."""

    clicked = Signal(str)  # (file_path)
    remove_requested = Signal(str)  # (file_path)

    ITEM_WIDTH = 180
    ITEM_HEIGHT = 240
    PREVIEW_WIDTH = 180
    PREVIEW_HEIGHT = 180

    def __init__(self, content_data: dict):
        super().__init__()
        self.content_data = content_data
        self.file_path = content_data.get("path", "")
        self.content_type = content_data.get("type", "")
        self._preview_pixmap = None
        self._setup_ui()

    def _setup_ui(self):
        """Set up the item UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Preview image
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setScaledContents(False)

        # Show placeholder initially
        self.set_loading_state()

        # Filename label
        filename = self.content_data.get("name", "Unknown")
        self.filename_label = QLabel(filename)
        self.filename_label.setWordWrap(True)
        self.filename_label.setTextFormat(Qt.PlainText)
        self.filename_label.setAlignment(Qt.AlignCenter)
        self.filename_label.setMaximumWidth(self.ITEM_WIDTH)

        # Metadata label (page count or duration)
        metadata_text = self._format_metadata()
        self.metadata_label = QLabel(metadata_text)
        self.metadata_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.preview_label)
        layout.addWidget(self.filename_label)
        layout.addWidget(self.metadata_label)
        layout.addStretch()

        self.setFixedSize(self.ITEM_WIDTH, self.ITEM_HEIGHT)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        # Set base style
        self.refresh_theme()

    def _format_metadata(self) -> str:
        """Format metadata text (page count or duration)."""
        if self.content_type == "pdf":
            page_count = self.content_data.get("page_count")
            if page_count is not None:
                return f"{page_count} pages"
            return "PDF"
        elif self.content_type == "video":
            duration_ms = self.content_data.get("duration_ms")
            if duration_ms is not None:
                # Convert to minutes:seconds
                total_seconds = duration_ms // 1000
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                return f"{minutes}:{seconds:02d}"
            return "Video"
        return ""

    def set_loading_state(self):
        """Show loading placeholder."""
        self.preview_label.setText("Loading...")
        self.preview_label.setStyleSheet(f"""
            QLabel {{
                background-color: {Theme.SURFACE_ALT};
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: {Theme.FONT_SIZE_CAPTION};
                border: 1px solid {Theme.BORDER};
            }}
        """)

    def set_error_state(self):
        """Show error placeholder."""
        self.preview_label.setText("Preview unavailable")
        self.preview_label.setStyleSheet(f"""
            QLabel {{
                background-color: {Theme.SURFACE_ALT};
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: {Theme.FONT_SIZE_CAPTION};
                border: 1px solid {Theme.BORDER};
            }}
        """)

    def set_preview(self, preview_path: str):
        """Set the preview image from file path."""
        pixmap = QPixmap(preview_path)
        if pixmap.isNull():
            self.set_error_state()
            return

        self._preview_pixmap = pixmap

        # Scale to fit preview area while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(
            self.PREVIEW_WIDTH,
            self.PREVIEW_HEIGHT,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.preview_label.setPixmap(scaled_pixmap)
        self.preview_label.setStyleSheet(f"""
            QLabel {{
                background-color: {Theme.SURFACE_ALT};
                border: 1px solid {Theme.BORDER};
            }}
        """)

    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.file_path)

    def contextMenuEvent(self, event: QContextMenuEvent):
        """Handle right-click context menu."""
        menu = QMenu(self)

        remove_action = menu.addAction("Remove from library")

        # Style the menu
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER_STRONG};
                border-radius: 6px;
                padding: 4px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: {Theme.FONT_SIZE_BODY};
            }}
            QMenu::item {{
                padding: 6px 12px;
                border-radius: 4px;
                color: {Theme.TEXT};
            }}
            QMenu::item:selected {{
                background-color: {Theme.ACCENT_SOFT};
            }}
        """)

        action = menu.exec_(event.globalPos())
        if action == remove_action:
            self.remove_requested.emit(self.file_path)

    def refresh_theme(self):
        """Refresh widget styling to match current theme."""
        self.filename_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: {Theme.FONT_SIZE_SUBHEAD};
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                padding: 8px 4px 2px 4px;
            }}
        """)
        self.metadata_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: {Theme.FONT_SIZE_CAPTION};
                padding: 2px 4px 4px 4px;
            }}
        """)
        self.setStyleSheet(f"""
            ContentBrowserItem {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER};
                border-radius: 8px;
            }}
            ContentBrowserItem:hover {{
                border-color: {Theme.ACCENT_BORDER};
            }}
        """)

        # Refresh preview label if in loading/error state
        if self._preview_pixmap is None:
            if "unavailable" in self.preview_label.text():
                self.set_error_state()
            else:
                self.set_loading_state()
        else:
            # Re-apply preview border
            self.preview_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.SURFACE_ALT};
                    border: 1px solid {Theme.BORDER};
                }}
            """)
