"""First-run checklist shown on the welcome screen.

Pure presentation: shows the state of each setup step and emits signals for
the actions. The main window decides when to show it and feeds it state.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from immersion_app.gui.theme import Theme

_STATE_GLYPHS = {"ok": "✓", "warning": "!", "error": "✕", "pending": "○", "checking": "…"}
_STATE_STYLES = {"ok": "ok", "warning": "warning", "error": "error", "pending": "muted", "checking": "muted"}


class _StepRow(QWidget):
    """One checklist line: status glyph, title + detail (one rich-text label), action button."""

    def __init__(self, title: str, button_text: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)
        self.glyph = QLabel(_STATE_GLYPHS["pending"])
        self.glyph.setFixedWidth(18)
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title = title
        self._detail = ""
        self.text = QLabel()
        self.text.setTextFormat(Qt.TextFormat.RichText)
        self.text.setWordWrap(True)
        self.button = QPushButton(button_text)
        self.button.setFixedSize(104, 32)
        layout.addWidget(self.glyph, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.state = "pending"

    @property
    def detail_text(self) -> str:
        return self._detail

    def set_state(self, state: str, detail: str = "", button_text: str | None = None) -> None:
        self.state = state
        self._detail = detail
        self.glyph.setText(_STATE_GLYPHS.get(state, "○"))
        if button_text is not None:
            self.button.setText(button_text)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.glyph.setStyleSheet(Theme.get_status_text_style(_STATE_STYLES.get(self.state, "muted")))
        self.text.setStyleSheet(f"QLabel {{ font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; }}")
        detail = html.escape(self._detail)
        detail_html = (
            f'<br><span style="color:{Theme.TEXT_SOFT}; font-size:12px;">{detail}</span>' if detail else ""
        )
        self.text.setText(
            f'<span style="color:{Theme.TEXT}; font-size:14px; font-weight:{Theme.FONT_WEIGHT_MEDIUM};">'
            f"{html.escape(self._title)}</span>{detail_html}"
        )
        self.button.setStyleSheet(Theme.get_button_style("secondary"))


class GettingStartedPanel(QFrame):
    settings_requested = Signal()
    start_anki_requested = Signal()
    open_requested = Signal()
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("GettingStartedPanel")
        self.setMinimumWidth(520)
        self.setMaximumWidth(640)
        # Never squash the rows when the welcome page is short on space.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.heading = QLabel("Getting started")
        self.hide_button = QPushButton("Hide")
        self.hide_button.setFixedHeight(24)
        self.hide_button.clicked.connect(self.dismissed.emit)
        header.addWidget(self.heading, 1)
        header.addWidget(self.hide_button)
        layout.addLayout(header)

        self.anki_step = _StepRow("Connect Anki", "Settings…")
        self.anki_step.button.clicked.connect(self._on_anki_button)
        self.language_step = _StepRow("Choose your languages", "Change…")
        self.language_step.button.clicked.connect(self.settings_requested.emit)
        self.open_step = _StepRow("Open a PDF or video", "Open…")
        self.open_step.button.clicked.connect(self.open_requested.emit)
        for step in (self.anki_step, self.language_step, self.open_step):
            layout.addWidget(step)

        self._anki_needs_start = False
        self.refresh_theme()

    # ---- state ---------------------------------------------------------
    def set_anki_state(self, state: str, detail: str = "", needs_start: bool = False) -> None:
        """``state``: ok / warning / error / checking. ``needs_start``: offer a Start Anki button."""
        self._anki_needs_start = needs_start
        self.anki_step.set_state(state, detail, "Start Anki" if needs_start else "Settings…")

    def set_languages(self, summary: str) -> None:
        self.language_step.set_state("ok", summary)

    def set_has_opened_content(self, opened: bool) -> None:
        self.open_step.set_state(
            "ok" if opened else "pending",
            "" if opened else "Click any word to translate · Ctrl+Space adds a card",
        )

    def is_complete(self) -> bool:
        return all(step.state == "ok" for step in (self.anki_step, self.language_step, self.open_step))

    def _on_anki_button(self) -> None:
        if self._anki_needs_start:
            self.start_anki_requested.emit()
        else:
            self.settings_requested.emit()

    def refresh_theme(self) -> None:
        self.setStyleSheet(f"""
            #GettingStartedPanel {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER_STRONG};
                border-radius: 10px;
            }}
            #GettingStartedPanel QWidget {{
                background-color: transparent;
            }}
        """)
        self.heading.setStyleSheet(Theme.get_label_style("heading"))
        self.hide_button.setStyleSheet(Theme.get_button_style("ghost"))
        for step in (self.anki_step, self.language_step, self.open_step):
            step.refresh_theme()
