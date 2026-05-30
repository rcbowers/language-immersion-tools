"""Derived activity analytics built from persisted usage sessions."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class SessionMetrics:
    session_date: date
    file_path: str
    file_type: str
    source_name: str
    active_seconds: int
    open_seconds: int
    pages_advanced: int
    minutes_advanced: float
    has_precise_pdf_metrics: bool
    has_precise_video_metrics: bool


class ActivityAnalyticsManager(QObject):
    """Aggregates persisted usage sessions into dashboard-friendly analytics."""

    stats_changed = Signal()

    def __init__(self, user_data: dict, anki_analytics=None, parent: QObject | None = None):
        super().__init__(parent)
        self._user_data = user_data
        self._anki_analytics = anki_analytics

    def refresh(self) -> None:
        """Notify listeners that underlying analytics data has changed."""
        self.stats_changed.emit()

    def get_dashboard_data(self, days: int = 30) -> dict:
        """Build a complete analytics snapshot for the dashboard."""
        sessions = self._collect_sessions()
        daily_records = self._build_daily_records(sessions)
        recent_daily_records = daily_records[: max(1, int(days))]
        today = date.today()
        today_record = next((record for record in daily_records if record["date"] == today.isoformat()), None)

        active_total = sum(session.active_seconds for session in sessions)
        open_total = sum(session.open_seconds for session in sessions)
        pdf_active = sum(session.active_seconds for session in sessions if session.file_type == "pdf")
        video_active = sum(session.active_seconds for session in sessions if session.file_type == "video")
        pdf_pages = sum(session.pages_advanced for session in sessions)
        video_minutes = sum(session.minutes_advanced for session in sessions)

        return {
            "summary": {
                "today_active_seconds": int(today_record["active_seconds"]) if today_record else 0,
                "today_open_seconds": int(today_record["open_seconds"]) if today_record else 0,
                "today_sources": int(len(today_record["sources"])) if today_record else 0,
                "total_active_seconds": active_total,
                "total_open_seconds": open_total,
                "pdf_pages_advanced": pdf_pages,
                "video_minutes_advanced": video_minutes,
                "current_streak_days": self._compute_current_streak(daily_records),
                "best_streak_days": self._compute_best_streak(daily_records),
                "cards_added_today": self._anki_analytics.today_count() if self._anki_analytics else 0,
                "vocabulary_total": self._anki_analytics.total_vocabulary_count() if self._anki_analytics else 0,
            },
            "trend": self._build_trend(daily_records, days=min(days, 14)),
            "daily_activity": recent_daily_records,
            "top_sources": self._build_top_sources(sessions),
            "mode_split": [
                {
                    "file_type": "pdf",
                    "label": "PDF",
                    "active_seconds": pdf_active,
                    "percentage": self._percentage(pdf_active, active_total),
                },
                {
                    "file_type": "video",
                    "label": "Video",
                    "active_seconds": video_active,
                    "percentage": self._percentage(video_active, active_total),
                },
            ],
            "efficiency": {
                "active_vs_open_ratio": self._percentage(active_total, open_total),
                "seven_day_active_seconds": sum(
                    record["active_seconds"]
                    for record in daily_records
                    if self._within_days(record["date"], 7)
                ),
                "thirty_day_active_seconds": sum(
                    record["active_seconds"]
                    for record in daily_records
                    if self._within_days(record["date"], 30)
                ),
            },
        }

    def _collect_sessions(self) -> list[SessionMetrics]:
        collected: list[SessionMetrics] = []
        usage_time = self._user_data.get("usage_time") or {}
        raw_sessions = usage_time.get("sessions")
        if not isinstance(raw_sessions, list):
            return collected

        for session in raw_sessions:
            if not isinstance(session, dict):
                continue
            try:
                session_date = datetime.fromisoformat(str(session.get("start_time"))).date()
            except (TypeError, ValueError):
                continue

            metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
            file_path = str(session.get("file_path") or "")
            file_type = str(session.get("file_type") or "")
            source_name = str(metadata.get("source_name") or os.path.basename(file_path) or "Unknown source")
            active_seconds = max(0, int(session.get("duration_seconds") or 0))
            open_seconds = max(active_seconds, int(session.get("elapsed_seconds") or active_seconds))

            pages_advanced, has_precise_pdf_metrics = self._extract_pdf_metrics(metadata)
            minutes_advanced, has_precise_video_metrics = self._extract_video_metrics(metadata)

            collected.append(
                SessionMetrics(
                    session_date=session_date,
                    file_path=file_path,
                    file_type=file_type,
                    source_name=source_name,
                    active_seconds=active_seconds,
                    open_seconds=open_seconds,
                    pages_advanced=pages_advanced,
                    minutes_advanced=minutes_advanced,
                    has_precise_pdf_metrics=has_precise_pdf_metrics,
                    has_precise_video_metrics=has_precise_video_metrics,
                )
            )

        collected.sort(key=lambda session: (session.session_date, session.active_seconds), reverse=True)
        return collected

    def _build_daily_records(self, sessions: list[SessionMetrics]) -> list[dict]:
        grouped: dict[date, list[SessionMetrics]] = defaultdict(list)
        for session in sessions:
            grouped[session.session_date].append(session)

        daily_records: list[dict] = []
        for session_date in sorted(grouped.keys(), reverse=True):
            day_sessions = grouped[session_date]
            source_groups: dict[tuple[str, str], dict] = {}

            for session in day_sessions:
                key = (session.file_path, session.file_type)
                source_entry = source_groups.setdefault(
                    key,
                    {
                        "source_name": session.source_name,
                        "file_type": session.file_type,
                        "active_seconds": 0,
                        "open_seconds": 0,
                        "pages_advanced": 0,
                        "minutes_advanced": 0.0,
                        "consumption_is_partial": False,
                    },
                )
                source_entry["active_seconds"] += session.active_seconds
                source_entry["open_seconds"] += session.open_seconds
                source_entry["pages_advanced"] += session.pages_advanced
                source_entry["minutes_advanced"] += session.minutes_advanced
                if session.file_type == "pdf" and not session.has_precise_pdf_metrics and session.pages_advanced == 0:
                    source_entry["consumption_is_partial"] = True
                if session.file_type == "video" and not session.has_precise_video_metrics and session.minutes_advanced == 0:
                    source_entry["consumption_is_partial"] = True

            sources = sorted(
                source_groups.values(),
                key=lambda entry: (entry["active_seconds"], entry["open_seconds"], entry["source_name"].lower()),
                reverse=True,
            )
            daily_records.append(
                {
                    "date": session_date.isoformat(),
                    "active_seconds": sum(session.active_seconds for session in day_sessions),
                    "open_seconds": sum(session.open_seconds for session in day_sessions),
                    "pages_advanced": sum(session.pages_advanced for session in day_sessions),
                    "minutes_advanced": sum(session.minutes_advanced for session in day_sessions),
                    "sources": sources,
                }
            )
        return daily_records

    def _build_top_sources(self, sessions: list[SessionMetrics], limit: int = 5) -> list[dict]:
        grouped: dict[tuple[str, str], dict] = {}
        for session in sessions:
            key = (session.file_path, session.file_type)
            entry = grouped.setdefault(
                key,
                {
                    "source_name": session.source_name,
                    "file_type": session.file_type,
                    "active_seconds": 0,
                    "open_seconds": 0,
                    "pages_advanced": 0,
                    "minutes_advanced": 0.0,
                },
            )
            entry["active_seconds"] += session.active_seconds
            entry["open_seconds"] += session.open_seconds
            entry["pages_advanced"] += session.pages_advanced
            entry["minutes_advanced"] += session.minutes_advanced

        return sorted(
            grouped.values(),
            key=lambda entry: (entry["active_seconds"], entry["open_seconds"], entry["source_name"].lower()),
            reverse=True,
        )[:limit]

    def _build_trend(self, daily_records: list[dict], days: int) -> list[dict]:
        today = date.today()
        record_map = {record["date"]: record for record in daily_records}
        trend = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            record = record_map.get(day.isoformat())
            trend.append(
                {
                    "date": day.isoformat(),
                    "active_seconds": int(record["active_seconds"]) if record else 0,
                    "open_seconds": int(record["open_seconds"]) if record else 0,
                }
            )
        return trend

    def _compute_current_streak(self, daily_records: list[dict]) -> int:
        if not daily_records:
            return 0
        record_dates = {datetime.fromisoformat(record["date"]).date() for record in daily_records}
        streak = 0
        cursor = date.today()
        while cursor in record_dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    def _compute_best_streak(self, daily_records: list[dict]) -> int:
        if not daily_records:
            return 0
        sorted_dates = sorted(datetime.fromisoformat(record["date"]).date() for record in daily_records)
        best = 0
        current = 0
        previous: date | None = None
        for day in sorted_dates:
            if previous is None or day == previous + timedelta(days=1):
                current += 1
            elif day != previous:
                current = 1
            best = max(best, current)
            previous = day
        return best

    def _extract_pdf_metrics(self, metadata: dict) -> tuple[int, bool]:
        if "pages_advanced" in metadata:
            return max(0, int(metadata.get("pages_advanced") or 0)), True

        start_page = self._parse_page_label(metadata.get("start_location"))
        end_page = self._parse_page_label(metadata.get("end_location"))
        if start_page is None or end_page is None:
            return 0, False
        return max(0, end_page - start_page), False

    def _extract_video_metrics(self, metadata: dict) -> tuple[float, bool]:
        if "minutes_advanced" in metadata:
            return max(0.0, float(metadata.get("minutes_advanced") or 0.0)), True

        start_seconds = self._parse_time_label(metadata.get("start_location"))
        end_seconds = self._parse_time_label(metadata.get("end_location"))
        if start_seconds is None or end_seconds is None:
            return 0.0, False
        return max(0.0, (end_seconds - start_seconds) / 60.0), False

    @staticmethod
    def _parse_page_label(label: object) -> int | None:
        match = re.search(r"page\s+(\d+)", str(label or ""), flags=re.IGNORECASE)
        if not match:
            return None
        return max(0, int(match.group(1)) - 1)

    @staticmethod
    def _parse_time_label(label: object) -> int | None:
        raw = str(label or "").strip()
        if not raw:
            return None
        parts = raw.split(":")
        if not all(part.isdigit() for part in parts):
            return None
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + int(seconds)
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        return None

    @staticmethod
    def _percentage(numerator: int | float, denominator: int | float) -> float:
        if denominator <= 0:
            return 0.0
        return round((float(numerator) / float(denominator)) * 100.0, 1)

    @staticmethod
    def _within_days(day_iso: str, max_days: int) -> bool:
        try:
            day = datetime.fromisoformat(day_iso).date()
        except ValueError:
            return False
        return (date.today() - day).days < max_days
