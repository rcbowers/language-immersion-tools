"""Activity analytics dialog."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from immersion_app.gui.theme import Theme


def _format_duration(seconds: int) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def _format_minutes(minutes: float) -> str:
    return f"{minutes:.1f} min"


class SummaryCard(QFrame):
    """Small metric card used at the top of the analytics dialog."""

    def __init__(self, title: str, value: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self._title = QLabel(title)
        self._value = QLabel(value)
        self._subtitle = QLabel(subtitle)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self._value)
        layout.addWidget(self._subtitle)

        self._subtitle.setWordWrap(True)
        self.refresh_theme()

    def set_content(self, title: str, value: str, subtitle: str = "") -> None:
        self._title.setText(title)
        self._value.setText(value)
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))

    def refresh_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
            }}
            """
        )
        self._title.setStyleSheet(
            f"color: {Theme.TEXT_MUTED}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_CAPTION};"
        )
        self._value.setStyleSheet(
            f"color: {Theme.TEXT}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_HEADING}; font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};"
        )
        self._subtitle.setStyleSheet(
            f"color: {Theme.TEXT_SOFT}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_CAPTION};"
        )


class TrendChart(QWidget):
    """Minimal recent activity chart."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list[dict] = []
        self.setMinimumHeight(92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_points(self, points: list[dict]) -> None:
        self._points = list(points)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(Theme.SURFACE))

        if not self._points:
            painter.end()
            return

        max_value = max(point.get("active_seconds", 0) for point in self._points) or 1
        bar_width = max(10, int(self.width() / max(len(self._points) * 1.8, 1)))
        gap = max(6, bar_width // 3)
        x = 12
        base_y = self.height() - 18
        for point in self._points:
            value = point.get("active_seconds", 0)
            height = int((value / max_value) * (self.height() - 34))
            painter.fillRect(x, base_y - height, bar_width, height, QColor(Theme.ACCENT))
            x += bar_width + gap

        painter.end()


class AnalyticsSection(QFrame):
    """Reusable framed section."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title_label = QLabel(title)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.body)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER};
                border-radius: 12px;
            }}
            """
        )
        self.title_label.setStyleSheet(
            f"color: {Theme.TEXT}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_SUBHEAD}; font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};"
        )


class ActivityAnalyticsDialog(QDialog):
    """Dedicated analytics view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Activity Analytics")
        self.resize(1040, 760)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root_layout.addWidget(self.scroll_area)

        self.content = QWidget()
        self.scroll_area.setWidget(self.content)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(16)

        self.header_label = QLabel("Study activity over time")
        self.header_label.setWordWrap(True)
        self.content_layout.addWidget(self.header_label)

        self.summary_grid = QGridLayout()
        self.summary_grid.setHorizontalSpacing(12)
        self.summary_grid.setVerticalSpacing(12)
        self.content_layout.addLayout(self.summary_grid)
        self.summary_cards = [SummaryCard("", "") for _ in range(6)]
        for index, card in enumerate(self.summary_cards):
            self.summary_grid.addWidget(card, index // 3, index % 3)

        self.trend_section = AnalyticsSection("Recent Trend")
        self.trend_chart = TrendChart()
        self.trend_caption = QLabel("")
        self.trend_section.body_layout.addWidget(self.trend_chart)
        self.trend_section.body_layout.addWidget(self.trend_caption)
        self.content_layout.addWidget(self.trend_section)

        row = QHBoxLayout()
        row.setSpacing(16)
        self.mode_split_section = AnalyticsSection("Mode Split")
        self.mode_split_body = self.mode_split_section.body_layout
        self.mode_split_body.setSpacing(8)

        self.top_sources_section = AnalyticsSection("Top Sources")
        self.top_sources_body = self.top_sources_section.body_layout
        self.top_sources_body.setSpacing(8)

        row.addWidget(self.mode_split_section, 1)
        row.addWidget(self.top_sources_section, 1)
        self.content_layout.addLayout(row)

        self.daily_section = AnalyticsSection("Daily Activity")
        self.daily_body = self.daily_section.body_layout
        self.daily_body.setSpacing(10)
        self.content_layout.addWidget(self.daily_section)

        self.empty_label = QLabel("No study sessions yet. Open a PDF or video and interact with it to start building analytics.")
        self.empty_label.setWordWrap(True)
        self.content_layout.addWidget(self.empty_label)

        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.setStyleSheet(f"QDialog {{ background-color: {Theme.BG}; }}")
        self.scroll_area.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: {Theme.BG}; }}"
        )
        self.content.setStyleSheet(f"QWidget {{ background-color: {Theme.BG}; }}")
        self.header_label.setStyleSheet(
            f"color: {Theme.TEXT}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_TITLE}; font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};"
        )
        self.trend_caption.setStyleSheet(
            f"color: {Theme.TEXT_SOFT}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_CAPTION};"
        )
        self.empty_label.setStyleSheet(
            f"color: {Theme.TEXT_SOFT}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_BODY}; padding: 24px;"
        )
        for card in self.summary_cards:
            card.refresh_theme()
        for section in (self.trend_section, self.mode_split_section, self.top_sources_section, self.daily_section):
            section.refresh_theme()

    def render_snapshot(self, snapshot: dict) -> None:
        summary = snapshot.get("summary", {})
        self.summary_cards[0].set_content("Today active", _format_duration(summary.get("today_active_seconds", 0)), "Focused study time today")
        self.summary_cards[1].set_content("Today open", _format_duration(summary.get("today_open_seconds", 0)), f"{summary.get('today_sources', 0)} sources touched today")
        self.summary_cards[2].set_content("Streak", f"{summary.get('current_streak_days', 0)} days", f"Best: {summary.get('best_streak_days', 0)} days")
        self.summary_cards[3].set_content("PDF progress", f"{summary.get('pdf_pages_advanced', 0)} pages", "Cumulative pages advanced")
        self.summary_cards[4].set_content("Video progress", _format_minutes(summary.get("video_minutes_advanced", 0.0)), "Cumulative playback advanced")
        self.summary_cards[5].set_content("Mining support", f"{summary.get('cards_added_today', 0)} cards today", f"{summary.get('vocabulary_total', 0)} vocab seen")

        trend = snapshot.get("trend", [])
        self.trend_chart.set_points(trend)
        self.trend_caption.setText(
            f"7d active: {_format_duration(snapshot.get('efficiency', {}).get('seven_day_active_seconds', 0))}   "
            f"30d active: {_format_duration(snapshot.get('efficiency', {}).get('thirty_day_active_seconds', 0))}   "
            f"active/open: {snapshot.get('efficiency', {}).get('active_vs_open_ratio', 0.0):.1f}%"
        )

        self._replace_rows(self.mode_split_body, [
            self._build_metric_row(
                item.get("label", ""),
                _format_duration(item.get("active_seconds", 0)),
                f"{item.get('percentage', 0.0):.1f}% of active time",
            )
            for item in snapshot.get("mode_split", [])
            if item.get("active_seconds", 0) > 0
        ])
        self._replace_rows(self.top_sources_body, [
            self._build_metric_row(
                item.get("source_name", ""),
                _format_duration(item.get("active_seconds", 0)),
                self._source_subtitle(item),
            )
            for item in snapshot.get("top_sources", [])
        ])
        self._replace_rows(self.daily_body, [self._build_day_card(day) for day in snapshot.get("daily_activity", [])])

        has_activity = bool(snapshot.get("daily_activity"))
        self.empty_label.setVisible(not has_activity)
        self.daily_section.setVisible(has_activity)
        self.trend_section.setVisible(has_activity)
        self.mode_split_section.setVisible(has_activity)
        self.top_sources_section.setVisible(has_activity)

    def _replace_rows(self, layout: QVBoxLayout, rows: list[QWidget]) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not rows:
            placeholder = QLabel("No data yet")
            placeholder.setStyleSheet(
                f"color: {Theme.TEXT_MUTED}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_CAPTION};"
            )
            layout.addWidget(placeholder)
            return
        for row in rows:
            layout.addWidget(row)
        layout.addStretch(1)

    def _build_metric_row(self, title: str, value: str, subtitle: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)
        title_label = QLabel(title)
        subtitle_label = QLabel(subtitle)
        title_label.setStyleSheet(
            f"color: {Theme.TEXT}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_BODY}; font-weight: {Theme.FONT_WEIGHT_MEDIUM};"
        )
        subtitle_label.setStyleSheet(
            f"color: {Theme.TEXT_SOFT}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_CAPTION};"
        )
        text_column.addWidget(title_label)
        text_column.addWidget(subtitle_label)
        layout.addLayout(text_column, 1)

        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_label.setStyleSheet(
            f"color: {Theme.TEXT}; font-family: {Theme.FONT_MONO}; font-size: {Theme.FONT_SIZE_SUBHEAD}; font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};"
        )
        layout.addWidget(value_label)
        return row

    def _build_day_card(self, day: dict) -> QWidget:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {Theme.SURFACE_ALT}; border: 1px solid {Theme.BORDER}; border-radius: 10px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        day_date = datetime.fromisoformat(day.get("date", datetime.now().date().isoformat())).date()
        title = QLabel(day_date.strftime("%A, %b %d"))
        title.setStyleSheet(
            f"color: {Theme.TEXT}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_SUBHEAD}; font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};"
        )
        totals = QLabel(
            f"Active {_format_duration(day.get('active_seconds', 0))}   "
            f"Open {_format_duration(day.get('open_seconds', 0))}   "
            f"PDF {int(day.get('pages_advanced', 0))} pages   "
            f"Video {_format_minutes(day.get('minutes_advanced', 0.0))}"
        )
        totals.setStyleSheet(
            f"color: {Theme.TEXT_SOFT}; font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK}; font-size: {Theme.FONT_SIZE_CAPTION};"
        )
        layout.addWidget(title)
        layout.addWidget(totals)

        for source in day.get("sources", []):
            layout.addWidget(
                self._build_metric_row(
                    source.get("source_name", ""),
                    _format_duration(source.get("active_seconds", 0)),
                    self._source_subtitle(source),
                )
            )
        return card

    @staticmethod
    def _source_subtitle(source: dict) -> str:
        if source.get("file_type") == "pdf":
            detail = f"{int(source.get('pages_advanced', 0))} pages advanced"
        else:
            detail = f"{_format_minutes(source.get('minutes_advanced', 0.0))} advanced"
        suffix = "partial history" if source.get("consumption_is_partial") else "exact history"
        return f"Open {_format_duration(source.get('open_seconds', 0))}   {detail}   {suffix}"
