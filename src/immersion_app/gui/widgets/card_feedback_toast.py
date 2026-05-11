"""Transient card feedback toast for add-to-Anki and queue actions."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from immersion_app.gui.theme import Theme


class CardFeedbackToast(QWidget):
    """Small overlay that shows a multi-line summary of the card action."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._current_variant = "added"
        self._build_ui()
        self._apply_variant("added")

    def _build_ui(self):
        self.setFixedWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.title_label = QLabel("")
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setStyleSheet(f"""
            QLabel {{
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
                background: transparent;
            }}
        """)
        layout.addWidget(self.title_label)

        self.body_label = QLabel("")
        self.body_label.setWordWrap(True)
        self.body_label.setTextFormat(Qt.TextFormat.PlainText)
        self.body_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_SOFT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
                line-height: 1.35;
                background: transparent;
            }}
        """)
        layout.addWidget(self.body_label)

    def _apply_variant(self, variant: str):
        self._current_variant = variant
        palette = self._variant_styles().get(variant, self._variant_styles()["queued"])
        self.setStyleSheet(f"""
            CardFeedbackToast {{
                background-color: {Theme.TOAST_BG};
                border: 1px solid {palette['border']};
                border-radius: 12px;
            }}
        """)
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {palette['title']};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
                background: {palette['badge_bg']};
                border-radius: 6px;
                padding: 4px 8px;
            }}
        """)

    def refresh_theme(self):
        self.body_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_SOFT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
                line-height: 1.35;
                background: transparent;
            }}
        """)
        self._apply_variant(self._current_variant)

    @staticmethod
    def _variant_styles():
        return {
            "added": {
                "border": Theme.ACCENT,
                "title": Theme.ACCENT_DARK,
                "badge_bg": Theme.ACCENT_SOFT,
                "badge_fg": Theme.ACCENT_DARK,
            },
            "queued": {
                "border": Theme.BORDER_STRONG,
                "title": Theme.TEXT,
                "badge_bg": Theme.SURFACE_ALT,
                "badge_fg": Theme.TEXT_SOFT,
            },
        }

    def show_message(self, title: str, body: str, variant: str = "added", timeout_ms: int = 6500):
        self._apply_variant(variant)
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.adjustSize()
        self.show()
        self.raise_()
        self._hide_timer.start(timeout_ms)
