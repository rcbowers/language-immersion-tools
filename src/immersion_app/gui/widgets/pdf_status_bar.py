"""
PDF status bar widget - floating bottom bar with word state legend.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from immersion_app.gui.theme import Theme


class PDFStatusBar(QWidget):
    """
    Floating status bar for PDF mode.

    Shows legend for word highlighting states.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(Theme.STATUS_BAR_HEIGHT)
        self._build_ui()

    def _build_ui(self):
        """Build the status bar UI."""
        self.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(255, 255, 255, 0.95);
                border-top: 1px solid {Theme.BORDER};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

        # Legend items
        legend_items = [
            ("□", Theme.HL_NEW, "New"),
            ("□", Theme.HL_SEEN, "Learning"),
            ("□", Theme.HL_SELECTED, "Selected"),
        ]

        for symbol, color, label in legend_items:
            # Color box
            color_box = QLabel(symbol)
            color_box.setFixedSize(16, 16)
            color_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            color_box.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border-radius: 3px;
                    font-size: 12px;
                    color: white;
                }}
            """)
            layout.addWidget(color_box)

            # Label text
            text_label = QLabel(label)
            text_label.setStyleSheet(f"""
                QLabel {{
                    color: {Theme.TEXT_SOFT};
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: 12px;
                    font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                }}
            """)
            layout.addWidget(text_label)

        layout.addStretch()

        # Instruction text
        instruction = QLabel("Click any word to translate · ⏎")
        instruction.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
            }}
        """)
        layout.addWidget(instruction)
