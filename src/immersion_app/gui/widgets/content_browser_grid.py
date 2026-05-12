"""Content browser grid widget with flow layout."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QLayout, QSizePolicy
from PySide6.QtCore import Signal, Qt, QRect, QSize, QPoint, QThreadPool

from ...core.content_browser_manager import ContentBrowserManager
from ...core.preview_generator import PreviewGenerator
from .content_browser_item import ContentBrowserItem
from ..theme import Theme


class FlowLayout(QLayout):
    """
    Flow layout that wraps items to next row when width is exceeded.

    Based on Qt example: https://doc.qt.io/qt-6/qtwidgets-layouts-flowlayout-example.html
    """

    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self._item_list = []
        self._h_spacing = spacing
        self._v_spacing = spacing

        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def horizontalSpacing(self):
        if self._h_spacing >= 0:
            return self._h_spacing
        else:
            return self._smart_spacing()

    def verticalSpacing(self):
        if self._v_spacing >= 0:
            return self._v_spacing
        else:
            return self._smart_spacing()

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())

        margin_left, margin_top, margin_right, margin_bottom = self.getContentsMargins()
        size += QSize(margin_left + margin_right, margin_top + margin_bottom)
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._item_list:
            widget = item.widget()
            space_x = self.horizontalSpacing()
            space_y = self.verticalSpacing()

            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + bottom

    def _smart_spacing(self):
        parent = self.parent()
        if parent is None:
            return -1
        elif parent.isWidgetType():
            return parent.style().layoutSpacing(
                QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal
            )
        else:
            return parent.spacing()


class ContentBrowserGrid(QWidget):
    """Content browser grid with preview thumbnails."""

    content_selected = Signal(str)  # (file_path)

    def __init__(
        self,
        content_browser_manager: ContentBrowserManager,
        preview_generator: PreviewGenerator,
        parent=None
    ):
        super().__init__(parent)
        self.content_browser_manager = content_browser_manager
        self.preview_generator = preview_generator
        self._thread_pool = QThreadPool.globalInstance()
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the grid UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create scroll area for grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setMinimumHeight(600)

        # Container for grid items with flow layout
        self.grid_container = QWidget()
        self.grid_layout = FlowLayout(self.grid_container, margin=0, spacing=16)

        self.scroll_area.setWidget(self.grid_container)
        main_layout.addWidget(self.scroll_area)

        # Populate grid
        self.refresh()
        self.refresh_theme()

    def _connect_signals(self):
        """Connect to content browser manager signals."""
        self.content_browser_manager.content_added.connect(self._on_content_changed)
        self.content_browser_manager.content_removed.connect(self._on_content_changed)
        self.content_browser_manager.content_updated.connect(self._on_content_changed)

        # Connect to preview generator signals
        self.preview_generator.preview_generated.connect(self._on_preview_generated)
        self.preview_generator.preview_failed.connect(self._on_preview_failed)

    def _on_content_changed(self, *args):
        """Handle content library changes."""
        self.refresh()

    def refresh(self):
        """Refresh the grid of content items."""
        # Clear existing items
        while self.grid_layout.count():
            child = self.grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Get all content
        content_items = self.content_browser_manager.get_all_content()

        if content_items:
            # Add each content item
            for content_data in content_items:
                item = ContentBrowserItem(content_data)
                item.clicked.connect(self.content_selected.emit)
                item.remove_requested.connect(self._on_remove_requested)
                self.grid_layout.addWidget(item)

                # Load preview (sync from cache or async generation)
                self._load_preview_for_item(item, content_data)
        else:
            # Show empty state
            empty_label = QLabel("No content yet\nOpen PDFs and videos to build your library")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"""
                QLabel {{
                    color: {Theme.TEXT_MUTED};
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: 14px;
                    padding: 60px 20px;
                }}
            """)
            self.grid_layout.addWidget(empty_label)

    def _load_preview_for_item(self, item: ContentBrowserItem, content_data: dict):
        """Load preview for a content item (sync from cache or async generation)."""
        preview_hash = content_data.get("preview_hash", "")
        content_type = content_data.get("type", "")
        file_path = content_data.get("path", "")

        # Try to load from cache first
        cached_preview = self.preview_generator.get_cached_preview(preview_hash, content_type)

        if cached_preview:
            # Load from cache immediately
            item.set_preview(cached_preview)
        else:
            # Generate preview asynchronously
            self.preview_generator.generate_preview(
                file_path,
                content_type,
                preview_hash,
                self._thread_pool
            )

    def _on_preview_generated(self, file_path: str, preview_path: str):
        """Handle preview generation success."""
        # Find the item widget for this file path and update it
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, ContentBrowserItem) and widget.file_path == file_path:
                widget.set_preview(preview_path)
                break

    def _on_preview_failed(self, file_path: str, error_message: str):
        """Handle preview generation failure."""
        # Find the item widget and set error state
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, ContentBrowserItem) and widget.file_path == file_path:
                widget.set_error_state()
                break

    def _on_remove_requested(self, file_path: str):
        """Handle remove request from item context menu."""
        self.content_browser_manager.remove_content(file_path)

    def refresh_theme(self):
        """Refresh styling to match current theme."""
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            {Theme.get_scrollbar_style()}
        """)

        # Refresh all item widgets
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if widget and hasattr(widget, "refresh_theme"):
                widget.refresh_theme()
