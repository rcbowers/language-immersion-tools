from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QLabel


class ClickablePdfLabel(QLabel):
    clicked = Signal(QPoint, object)
    hovered = Signal(QPoint, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(event.position().toPoint(), event.modifiers())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.hovered.emit(event.position().toPoint(), event.modifiers())
        super().mouseMoveEvent(event)
