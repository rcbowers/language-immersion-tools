"""
PDF status bar widget - floating bottom bar with word state legend.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from immersion_app.gui.theme import Theme


class PDFStatusBar(QWidget):
    """
    Floating status bar for PDF mode.

    Shows legend for word highlighting states and zoom controls.
    """

    # Zoom control signals
    zoom_out_clicked = Signal()
    zoom_in_clicked = Signal()
    fit_width_clicked = Signal()
    reset_zoom_clicked = Signal()

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

        # Zoom controls
        zoom_container = QWidget()
        zoom_layout = QHBoxLayout(zoom_container)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(8)

        # Zoom percentage label (clickable to reset)
        self.zoom_label = QLabel("200%")
        self.zoom_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_SOFT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                padding: 4px 8px;
                border-radius: 4px;
                background-color: transparent;
            }}
            QLabel:hover {{
                background-color: {Theme.SURFACE_ALT};
                cursor: pointer;
            }}
        """)
        self.zoom_label.mousePressEvent = lambda e: self.reset_zoom_clicked.emit()
        self.zoom_label.setToolTip("Click to reset zoom to 100%")
        zoom_layout.addWidget(self.zoom_label)

        # Zoom out button
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedSize(24, 24)
        zoom_out_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Theme.TEXT_SOFT};
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: {Theme.FONT_WEIGHT_BOLD};
            }}
            QPushButton:hover {{
                background-color: {Theme.SURFACE_ALT};
            }}
        """)
        zoom_out_btn.setToolTip("Zoom out (Ctrl+-)")
        zoom_out_btn.clicked.connect(self.zoom_out_clicked.emit)
        zoom_layout.addWidget(zoom_out_btn)

        # Zoom in button
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(24, 24)
        zoom_in_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Theme.TEXT_SOFT};
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: {Theme.FONT_WEIGHT_BOLD};
            }}
            QPushButton:hover {{
                background-color: {Theme.SURFACE_ALT};
            }}
        """)
        zoom_in_btn.setToolTip("Zoom in (Ctrl++)")
        zoom_in_btn.clicked.connect(self.zoom_in_clicked.emit)
        zoom_layout.addWidget(zoom_in_btn)

        # Fit to width button
        fit_width_btn = QPushButton("⤢")
        fit_width_btn.setFixedSize(24, 24)
        fit_width_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Theme.TEXT_SOFT};
                border: none;
                border-radius: 12px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {Theme.SURFACE_ALT};
            }}
        """)
        fit_width_btn.setToolTip("Fit to width (Ctrl+0)")
        fit_width_btn.clicked.connect(self.fit_width_clicked.emit)
        zoom_layout.addWidget(fit_width_btn)

        layout.addWidget(zoom_container)

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

    def set_zoom_level(self, zoom_factor: float):
        """Update the zoom percentage display."""
        percentage = int(zoom_factor * 100)
        self.zoom_label.setText(f"{percentage}%")
