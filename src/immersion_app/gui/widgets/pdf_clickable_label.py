from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QRegion
from PySide6.QtWidgets import QLabel


class ClickablePdfLabel(QLabel):
    """Shows a cached page pixmap and paints word/selection highlights on top of it.

    The page image is set once per page/zoom/theme; highlights are lightweight
    overlay rectangles, so moving a selection only repaints the affected area.
    """

    clicked = Signal(QPoint, object)
    hovered = Signal(QPoint, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._word_highlights: list[tuple[QRect, QColor]] = []
        self._selection_rects: list[QRect] = []
        self._selection_color = QColor(255, 220, 0, 110)

    def set_word_highlights(self, items: list[tuple[QRect, QColor]]) -> None:
        """Seen/new word backgrounds, as ``(rect, color)`` in label pixel coordinates."""
        self._word_highlights = list(items)
        self.update()

    def set_selection_rects(self, rects: list[QRect], color: QColor | None = None) -> None:
        """Selection highlight rects. Only the union of old and new areas is repainted."""
        if color is not None:
            self._selection_color = color
        new_rects = list(rects)
        if new_rects == self._selection_rects:
            return
        dirty = QRegion()
        for rect in self._selection_rects + new_rects:
            dirty += rect.adjusted(-1, -1, 1, 1)
        self._selection_rects = new_rects
        self.update(dirty)

    def paintEvent(self, event):
        super().paintEvent(event)  # cached page pixmap
        if not self._word_highlights and not self._selection_rects:
            return
        clip = event.rect()
        painter = QPainter(self)
        for rect, color in self._word_highlights:
            if rect.intersects(clip):
                painter.fillRect(rect, color)
        for rect in self._selection_rects:
            if rect.intersects(clip):
                painter.fillRect(rect, self._selection_color)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(event.position().toPoint(), event.modifiers())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.hovered.emit(event.position().toPoint(), event.modifiers())
        super().mouseMoveEvent(event)
