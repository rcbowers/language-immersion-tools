"""PDF status bar widget for word-state legend and compact controls."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from immersion_app.gui.theme import Theme


class ClickableStatusLabel(QLabel):
    """Small helper label that can act like a button when enabled."""

    clicked = Signal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._clickable = False

    def set_clickable(self, clickable: bool):
        self._clickable = clickable
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor
        )

    def mousePressEvent(self, event):
        if self._clickable and (event is None or event.button() == Qt.MouseButton.LeftButton):
            self.clicked.emit()
        if event is not None:
            super().mousePressEvent(event)


class PDFStatusBar(QWidget):
    """
    Floating status bar for PDF mode.

    Shows legend for word highlighting states and compact controls.
    """

    zoom_out_clicked = Signal()
    zoom_in_clicked = Signal()
    fit_width_clicked = Signal()
    reset_zoom_clicked = Signal()
    anki_status_clicked = Signal()
    translation_mode_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(Theme.STATUS_BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._legend_boxes = []
        self._legend_labels = []
        self._build_ui()

    def _build_ui(self):
        """Build the status bar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 2, 12, 2)
        layout.setSpacing(10)

        left_region = QWidget()
        left_layout = QHBoxLayout(left_region)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        legend_items = [
            (Theme.HL_NEW, "New"),
            (Theme.HL_SEEN, "Learning"),
            (Theme.HL_SELECTED, "Selected"),
        ]

        for color, label in legend_items:
            color_box = QLabel()
            color_box.setFixedSize(16, 16)
            color_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            left_layout.addWidget(color_box, alignment=Qt.AlignmentFlag.AlignVCenter)
            self._legend_boxes.append((color_box, color))

            text_label = QLabel(label)
            left_layout.addWidget(text_label, alignment=Qt.AlignmentFlag.AlignVCenter)
            self._legend_labels.append(text_label)

        left_layout.addStretch()
        layout.addWidget(left_region, stretch=1)

        center_region = QWidget()
        center_layout = QHBoxLayout(center_region)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.instruction_label = QLabel(
            "Click word or Ctrl+hover to translate · Shift+click to end of a phrase · Ctrl+Space to add to Anki"
        )
        self.instruction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
            }}
        """)
        center_layout.addWidget(self.instruction_label)
        layout.addWidget(center_region, stretch=1)

        right_region = QWidget()
        right_layout = QHBoxLayout(right_region)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.usage_tracking_label = QLabel("○")
        self.usage_tracking_label.setToolTip("Usage tracking: Idle")
        self.usage_tracking_label.setStyleSheet(self._get_usage_tracking_style(active=False))
        right_layout.addWidget(self.usage_tracking_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.translation_mode_label = ClickableStatusLabel("Translation: Offline")
        self.translation_mode_label.set_clickable(True)
        self.translation_mode_label.setToolTip("Click to toggle online/offline translation")
        self.translation_mode_label.clicked.connect(self.translation_mode_clicked.emit)
        self.translation_mode_label.setStyleSheet(self._get_clickable_badge_style())
        right_layout.addWidget(self.translation_mode_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.anki_status_label = ClickableStatusLabel("Anki: Checking...")
        self.anki_status_label.setStyleSheet(self._get_badge_style())
        self.anki_status_label.setToolTip("Click to retry the Anki connection check")
        self.anki_status_label.clicked.connect(self.anki_status_clicked.emit)
        right_layout.addWidget(self.anki_status_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        zoom_container = QWidget()
        zoom_layout = QHBoxLayout(zoom_container)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(4)

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
            }}
        """)
        self.zoom_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_label.mousePressEvent = lambda e: self.reset_zoom_clicked.emit()
        self.zoom_label.setToolTip("Click to reset zoom to 100%")
        zoom_layout.addWidget(self.zoom_label)

        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setFixedSize(24, 24)
        zoom_out_btn.setStyleSheet(self._get_zoom_button_style())
        zoom_out_btn.setToolTip("Zoom out (Ctrl+-)")
        zoom_out_btn.clicked.connect(self.zoom_out_clicked.emit)
        zoom_layout.addWidget(zoom_out_btn)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(24, 24)
        zoom_in_btn.setStyleSheet(self._get_zoom_button_style())
        zoom_in_btn.setToolTip("Zoom in (Ctrl++)")
        zoom_in_btn.clicked.connect(self.zoom_in_clicked.emit)
        zoom_layout.addWidget(zoom_in_btn)

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
        self.fit_width_button = fit_width_btn
        self.zoom_out_button = zoom_out_btn
        self.zoom_in_button = zoom_in_btn

        right_layout.addWidget(zoom_container, alignment=Qt.AlignmentFlag.AlignVCenter)
        right_layout.addStretch()
        layout.addWidget(right_region, stretch=1)

        self.set_anki_status(connected=False, checking=True)
        self.refresh_theme()

    def _get_badge_style(self) -> str:
        return f"""
            QLabel {{
                color: {Theme.TEXT_SOFT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                padding: 3px 8px;
                border-radius: 4px;
                background-color: {Theme.SURFACE_ALT};
            }}
        """

    def _get_clickable_badge_style(self) -> str:
        return f"""
            QLabel {{
                color: {Theme.TEXT_SOFT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                padding: 3px 8px;
                border-radius: 4px;
                background-color: {Theme.SURFACE_ALT};
            }}
            QLabel:hover {{
                background-color: {Theme.BORDER};
            }}
        """

    def _get_usage_tracking_style(self, active: bool) -> str:
        """Get style for usage tracking indicator."""
        color = "#4CAF50" if active else Theme.TEXT_MUTED  # Green when active, muted when idle
        return f"""
            QLabel {{
                color: {color};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 14px;
                font-weight: {Theme.FONT_WEIGHT_BOLD};
                padding: 2px 6px;
                border-radius: 4px;
                background-color: transparent;
            }}
        """

    def _get_zoom_button_style(self) -> str:
        return f"""
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
        """

    def refresh_theme(self):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.SURFACE_OVERLAY};
                border-top: 1px solid {Theme.BORDER};
            }}
        """)
        for color_box, color in self._legend_boxes:
            color_box.setStyleSheet(f"""
                QLabel {{
                    background-color: {color};
                    border: 1px solid {Theme.BORDER_STRONG};
                    border-radius: 3px;
                }}
            """)
        for text_label in self._legend_labels:
            text_label.setStyleSheet(f"""
                QLabel {{
                    color: {Theme.TEXT_SOFT};
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: 12px;
                    font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                }}
            """)
        self.instruction_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
            }}
        """)
        self.translation_mode_label.setStyleSheet(self._get_clickable_badge_style())
        self.anki_status_label.setStyleSheet(self._get_badge_style())
        # Usage tracking indicator gets its own style
        is_active = self.usage_tracking_label.text() == "●"
        self.usage_tracking_label.setStyleSheet(self._get_usage_tracking_style(is_active))
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
            }}
        """)
        self.zoom_out_button.setStyleSheet(self._get_zoom_button_style())
        self.zoom_in_button.setStyleSheet(self._get_zoom_button_style())
        self.fit_width_button.setStyleSheet(f"""
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

    def set_zoom_level(self, zoom_factor: float):
        """Update the zoom percentage display."""
        percentage = int(zoom_factor * 100)
        self.zoom_label.setText(f"{percentage}%")

    def set_translation_mode(self, mode: str):
        """Update the translation mode display."""
        mode_text = "Online" if mode == "online" else "Offline"
        self.translation_mode_label.setText(f"Translation: {mode_text}")

    def set_anki_status(self, connected: bool, checking: bool = False):
        """Update Anki status text and clickability."""
        if checking:
            self.anki_status_label.setText("Anki: Checking...")
            self.anki_status_label.set_clickable(False)
            return

        if connected:
            self.anki_status_label.setText("Anki: Connected \u2713")
            self.anki_status_label.set_clickable(False)
            return

        self.anki_status_label.setText("Anki: Not connected")
        self.anki_status_label.set_clickable(True)

    def set_usage_tracking_active(self, active: bool):
        """Update usage tracking indicator."""
        if active:
            self.usage_tracking_label.setText("●")
            self.usage_tracking_label.setToolTip("Usage tracking: Active (recording time)")
        else:
            self.usage_tracking_label.setText("○")
            self.usage_tracking_label.setToolTip("Usage tracking: Idle")
        self.usage_tracking_label.setStyleSheet(self._get_usage_tracking_style(active))
