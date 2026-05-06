"""
Chapter rail widget for PDF navigation.

Shows a vertical list of chapter markers with page numbers.
"""

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtGui import QPainter, QColor

from immersion_app.gui.theme import Theme


class ChapterRail(QWidget):
    """
    Vertical chapter navigation rail for PDFs.

    Shows circular markers for each chapter in the document outline.
    """

    chapter_clicked = Signal(int)  # page number

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedWidth(Theme.CHAPTER_RAIL_WIDTH)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.SURFACE};
                border-left: 1px solid {Theme.BORDER};
            }}
        """)

        # Chapter data: list of (title, page_number)
        self.chapters = []
        self.current_page = 0
        self.total_pages = 1

        # Build UI
        self._build_ui()

    def _build_ui(self):
        """Build the rail UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(0)

        # Chapters will be drawn manually in paintEvent
        layout.addStretch()

        # Page counter at bottom
        self.page_counter = QLabel("0/0")
        self.page_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_counter.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_MONO};
                font-size: {Theme.FONT_SIZE_MICRO};
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                padding: 8px 0px;
            }}
        """)
        layout.addWidget(self.page_counter)

    def set_chapters(self, toc_entries, total_pages):
        """
        Set the chapter list from PDF table of contents.

        Args:
            toc_entries: List of tuples (level, title, page_number)
            total_pages: Total pages in document
        """
        # Extract only top-level chapters (level 1)
        self.chapters = [
            (title, page) for level, title, page in toc_entries if level == 1
        ]
        self.total_pages = total_pages
        self.update()

    def set_current_page(self, page_number):
        """Update the current page number."""
        self.current_page = page_number
        self.page_counter.setText(f"{page_number}/{self.total_pages}")
        self.update()

    def paintEvent(self, event):
        """Draw chapter markers."""
        super().paintEvent(event)

        if not self.chapters or self.total_pages <= 1:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Available height for markers (excluding page counter)
        counter_height = self.page_counter.height()
        available_height = self.height() - counter_height - 32  # 32 for margins

        # Calculate marker positions
        marker_radius = 4
        center_x = self.width() // 2

        for title, page_num in self.chapters:
            # Calculate vertical position based on page ratio
            ratio = (page_num - 1) / max(1, self.total_pages - 1)
            y_pos = 16 + int(ratio * available_height)

            # Determine if this is the current chapter
            is_current = self._is_current_chapter(page_num)

            # Draw marker
            if is_current:
                color = Theme.to_qcolor(Theme.ACCENT)
            else:
                color = Theme.to_qcolor(Theme.BORDER_STRONG)

            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                center_x - marker_radius,
                y_pos - marker_radius,
                marker_radius * 2,
                marker_radius * 2
            )

    def _is_current_chapter(self, chapter_page):
        """Check if the given chapter page is the current one."""
        # Find which chapter the current page belongs to
        current_chapter_page = 1
        for title, page_num in self.chapters:
            if page_num <= self.current_page:
                current_chapter_page = page_num
            else:
                break
        return chapter_page == current_chapter_page

    def mousePressEvent(self, event):
        """Handle clicks on chapter markers."""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if not self.chapters or self.total_pages <= 1:
            return

        # Find clicked chapter
        counter_height = self.page_counter.height()
        available_height = self.height() - counter_height - 32
        click_y = event.position().y()

        marker_radius = 8  # Larger hit area
        center_x = self.width() // 2

        for title, page_num in self.chapters:
            ratio = (page_num - 1) / max(1, self.total_pages - 1)
            y_pos = 16 + int(ratio * available_height)

            # Check if click is near this marker
            distance = abs(click_y - y_pos)
            if distance <= marker_radius:
                self.chapter_clicked.emit(page_num)
                break
