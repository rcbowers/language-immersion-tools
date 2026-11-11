"""State manager for usage time tracking."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, Signal

from immersion_app.core.user_data import save_user_data


IDLE_TIMEOUT_SECONDS = 120
WINDOW_HALF_SIZE_SECONDS = 60
STATUS_CHECK_INTERVAL_MS = 5000


class UsageTimeTracker(QObject):
    """
    Manages usage time tracking.

    Single source of truth for tracking active usage time when the app is focused.

    A *file context* exists while a PDF or video is open. Within it, activity is
    grouped into *segments*: a segment begins with the first activity and ends
    after ``IDLE_TIMEOUT_SECONDS`` without activity (or when the file closes).
    Each finished segment is saved as one session record (split at local
    midnight), and the next activity on the same file starts a new segment.
    """

    session_started = Signal(str, str)  # (file_path, file_type)
    session_ended = Signal(str, int)  # (file_path, duration_seconds)
    stats_updated = Signal(int, int)  # (today_seconds, total_seconds)
    active_status_changed = Signal(bool)  # (is_active)

    def __init__(self, user_data: dict):
        super().__init__()
        self._user_data = user_data
        self._ensure_usage_time_section()

        # In-memory session state
        self._activity_buffer: list[datetime] = []
        self._current_file_path: str = ""
        self._current_file_type: str = ""
        self._session_start_time: datetime | None = None
        self._session_start_location: str = ""
        self._current_location: str = ""
        self._start_page_index: int | None = None
        self._current_page_index: int | None = None
        self._start_position_ms: int | None = None
        self._current_position_ms: int | None = None
        self._is_window_focused: bool = False

        # Inactivity timer: keeps the active indicator fresh and closes idle segments
        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.timeout.connect(self._check_inactivity)
        self._inactivity_timer.start(STATUS_CHECK_INTERVAL_MS)

        # Active status tracking
        self._is_active = False

    def _ensure_usage_time_section(self) -> dict:
        """Ensure usage_time section exists in user data."""
        usage_time = self._user_data.setdefault("usage_time", {})
        sessions = usage_time.get("sessions")
        usage_time["sessions"] = sessions if isinstance(sessions, list) else []
        try:
            usage_time["total_seconds"] = int(usage_time.get("total_seconds") or 0)
        except (TypeError, ValueError):
            usage_time["total_seconds"] = 0
        usage_time["last_activity_timestamp"] = str(usage_time.get("last_activity_timestamp") or "")
        return usage_time

    def _normalize_path(self, file_path: str) -> str:
        """Normalize file path for consistent storage (Windows-compatible)."""
        return os.path.normcase(os.path.abspath(file_path))

    def set_window_focused(self, focused: bool) -> None:
        """Track window focus state."""
        self._is_window_focused = focused
        self._update_active_status()

    def on_document_loaded(self, file_path: str, page_count: int = 0) -> None:
        """Session start for PDF documents."""
        # Finalize previous file context if one is open
        if self._current_file_path or self._session_start_time is not None:
            self.finalize_current_session()

        # Start new session
        self._current_file_path = self._normalize_path(file_path)
        self._current_file_type = "pdf"
        self._session_start_time = datetime.now()
        self._session_start_location = "Page 1"
        self._current_location = "Page 1"
        self._start_page_index = None
        self._current_page_index = None
        self._start_position_ms = None
        self._current_position_ms = None
        self._activity_buffer.clear()

        self.session_started.emit(file_path, "pdf")
        self._update_active_status()

    def on_document_closed(self) -> None:
        """Session end for PDF documents."""
        self.finalize_current_session()

    def on_video_loaded(self, file_path: str) -> None:
        """Session start for video."""
        # Finalize previous file context if one is open
        if self._current_file_path or self._session_start_time is not None:
            self.finalize_current_session()

        # Start new session
        self._current_file_path = self._normalize_path(file_path)
        self._current_file_type = "video"
        self._session_start_time = datetime.now()
        self._session_start_location = "00:00:00"
        self._current_location = "00:00:00"
        self._start_page_index = None
        self._current_page_index = None
        self._start_position_ms = None
        self._current_position_ms = None
        self._activity_buffer.clear()

        self.session_started.emit(file_path, "video")
        self._update_active_status()

    def on_video_closed(self) -> None:
        """Session end for video."""
        self.finalize_current_session()

    def update_location(self, location: str) -> None:
        """Update current location (page number, video timestamp, etc.)."""
        self._current_location = location

    def set_pdf_page_index(self, page_index: int) -> None:
        """Track the current PDF page for analytics and location metadata."""
        normalized_index = max(0, int(page_index))
        self._current_page_index = normalized_index
        self._current_location = f"Page {normalized_index + 1}"
        if self._current_file_type == "pdf" and self._start_page_index is None:
            self._start_page_index = normalized_index
            self._session_start_location = self._current_location

    def set_video_position_ms(self, position_ms: int) -> None:
        """Track the current video playback position for analytics and location metadata."""
        normalized_position = max(0, int(position_ms))
        self._current_position_ms = normalized_position
        self._current_location = self._format_duration(normalized_position // 1000)
        if self._current_file_type == "video" and self._start_position_ms is None:
            self._start_position_ms = normalized_position
            self._session_start_location = self._current_location

    def record_activity(self) -> None:
        """Record user activity (only while focused with a file open).

        If the previous segment was closed for inactivity, this starts a new
        segment on the same file rather than being ignored.
        """
        if not self._is_window_focused:
            return

        if not self._current_file_path:
            return

        now = datetime.now()
        if self._session_start_time is None:
            self._begin_segment(now)
        self._activity_buffer.append(now)

        # Update last activity timestamp in user data (for potential crash recovery)
        self._user_data["usage_time"]["last_activity_timestamp"] = now.isoformat()

        # Update active status
        self._update_active_status()

    def _begin_segment(self, start_time: datetime) -> None:
        """Start a new activity segment within the current file context.

        Start location/page/position were captured when the previous segment
        closed, so navigation that happened while idle still counts as progress.
        """
        self._session_start_time = start_time
        self._activity_buffer.clear()

    def finalize_current_session(self) -> None:
        """Save the current segment and close the file context."""
        self._close_segment()
        self._reset_session_state()

    def _close_segment(self) -> None:
        """Save the current activity segment (if any) but keep the file context open."""
        if self._session_start_time is None:
            return

        if not self._activity_buffer:
            # No activity recorded, don't save session
            self._clear_segment()
            return

        merged_windows = self._merged_activity_windows()
        duration_seconds = int(sum(end - start for start, end in merged_windows))
        if duration_seconds <= 0:
            self._clear_segment()
            return

        session_end_time = datetime.now()
        day_chunks = self._split_windows_by_day(merged_windows)
        session_records = []
        for index, (day_start, day_end, day_seconds) in enumerate(day_chunks):
            if day_seconds <= 0:
                continue
            record_start = self._session_start_time if index == 0 else day_start
            record_end = session_end_time if index == len(day_chunks) - 1 else day_end
            session_records.append(
                self._build_session_record(record_start, max(record_start, record_end), day_seconds)
            )

        for record in session_records:
            self._user_data["usage_time"]["sessions"].append(record)
            self._user_data["usage_time"]["total_seconds"] += record["duration_seconds"]
        self._user_data["usage_time"]["last_activity_timestamp"] = session_end_time.isoformat()

        save_user_data(self._user_data)

        # Emit signals
        self.session_ended.emit(self._current_file_path, duration_seconds)
        self.stats_updated.emit(
            self.get_today_usage_seconds(),
            self.get_total_usage_seconds()
        )

        self._clear_segment()

    def _build_session_record(self, start_time: datetime, end_time: datetime, duration_seconds: int) -> dict:
        elapsed_seconds = max(duration_seconds, max(0, int((end_time - start_time).total_seconds())))
        metadata = {
            "source_name": os.path.basename(self._current_file_path) if self._current_file_path else "",
            "start_location": self._session_start_location,
            "end_location": self._current_location,
        }
        if self._current_file_type == "pdf":
            start_page_index = self._start_page_index if self._start_page_index is not None else 0
            end_page_index = self._current_page_index if self._current_page_index is not None else start_page_index
            metadata["start_page_index"] = start_page_index
            metadata["end_page_index"] = end_page_index
            metadata["pages_advanced"] = max(0, end_page_index - start_page_index)
        elif self._current_file_type == "video":
            start_position_ms = self._start_position_ms if self._start_position_ms is not None else 0
            end_position_ms = self._current_position_ms if self._current_position_ms is not None else start_position_ms
            metadata["start_position_ms"] = start_position_ms
            metadata["end_position_ms"] = end_position_ms
            metadata["minutes_advanced"] = max(0.0, (end_position_ms - start_position_ms) / 60000.0)

        return {
            "file_path": self._current_file_path,
            "file_type": self._current_file_type,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": int(duration_seconds),
            "elapsed_seconds": elapsed_seconds,
            "metadata": metadata,
        }

    def _clear_segment(self) -> None:
        """Forget the current segment; the next activity starts a new one."""
        self._activity_buffer.clear()
        self._session_start_time = None
        # The next segment starts where this one ended.
        self._session_start_location = self._current_location
        self._start_page_index = self._current_page_index
        self._start_position_ms = self._current_position_ms
        self._update_active_status()

    def _reset_session_state(self) -> None:
        """Clear all in-memory state, including the file context."""
        self._activity_buffer.clear()
        self._current_file_path = ""
        self._current_file_type = ""
        self._session_start_time = None
        self._session_start_location = ""
        self._current_location = ""
        self._start_page_index = None
        self._current_page_index = None
        self._start_position_ms = None
        self._current_position_ms = None
        self._update_active_status()

    def _merged_activity_windows(self) -> list[tuple[float, float]]:
        """Merge the ±60 s window around each activity into non-overlapping ranges (epoch seconds)."""
        merged: list[list[float]] = []
        for activity_time in sorted(self._activity_buffer):
            timestamp = activity_time.timestamp()
            start = timestamp - WINDOW_HALF_SIZE_SECONDS
            end = timestamp + WINDOW_HALF_SIZE_SECONDS
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return [(start, end) for start, end in merged]

    @staticmethod
    def _split_windows_by_day(windows: list[tuple[float, float]]) -> list[tuple[datetime, datetime, int]]:
        """Split merged windows at local midnight.

        Returns ``(first_moment, last_moment, active_seconds)`` per calendar day,
        so time spent after midnight is credited to the new day.
        """
        by_day: dict = {}
        for start, end in windows:
            cursor = start
            while cursor < end:
                cursor_dt = datetime.fromtimestamp(cursor)
                next_midnight = datetime.combine(cursor_dt.date() + timedelta(days=1), datetime.min.time())
                chunk_end = min(end, next_midnight.timestamp())
                day = cursor_dt.date()
                first, last, total = by_day.get(day, (cursor, chunk_end, 0.0))
                by_day[day] = (min(first, cursor), max(last, chunk_end), total + (chunk_end - cursor))
                cursor = chunk_end
        result = []
        for day in sorted(by_day):
            first, last, total = by_day[day]
            result.append((datetime.fromtimestamp(first), datetime.fromtimestamp(last), int(round(total))))
        # Keep the per-day sum equal to the merged total despite rounding.
        expected = int(sum(end - start for start, end in windows))
        drift = expected - sum(item[2] for item in result)
        if result and drift:
            day_start, day_end, seconds = result[-1]
            result[-1] = (day_start, day_end, seconds + drift)
        return result

    def _calculate_session_duration(self) -> int:
        """Total active seconds for the current segment (merged ±60 s activity windows)."""
        return int(sum(end - start for start, end in self._merged_activity_windows()))

    def _check_inactivity(self) -> None:
        """Refresh the active indicator and close the segment after the idle timeout."""
        self._update_active_status()

        if self._session_start_time is None or not self._activity_buffer:
            return

        time_since_last_activity = (datetime.now() - max(self._activity_buffer)).total_seconds()
        if time_since_last_activity > IDLE_TIMEOUT_SECONDS:
            # Close the idle segment but keep the file open so the user's
            # next action resumes tracking.
            self._close_segment()

    def get_today_usage_seconds(self) -> int:
        """Get total usage time for today."""
        today = datetime.now().date()
        total_seconds = 0

        for session in self._user_data["usage_time"]["sessions"]:
            try:
                session_date = datetime.fromisoformat(session["start_time"]).date()
                if session_date == today:
                    total_seconds += session.get("duration_seconds", 0)
            except (ValueError, KeyError):
                continue

        return total_seconds

    def get_total_usage_seconds(self) -> int:
        """Get total usage time across all sessions."""
        return self._user_data["usage_time"]["total_seconds"]

    def get_file_usage_seconds(self, file_path: str) -> int:
        """Get total usage time for a specific file."""
        normalized_path = self._normalize_path(file_path)
        total_seconds = 0

        for session in self._user_data["usage_time"]["sessions"]:
            if session.get("file_path") == normalized_path:
                total_seconds += session.get("duration_seconds", 0)

        return total_seconds

    def is_currently_active(self) -> bool:
        """
        Check if usage tracking is currently active.

        Active means:
        - Session is running (file is loaded)
        - Window is focused
        - Recent activity within the idle timeout
        """
        if self._session_start_time is None:
            return False

        if not self._is_window_focused:
            return False

        if not self._activity_buffer:
            return False

        # Check if there's been activity in the last 2 minutes
        now = datetime.now()
        last_activity = max(self._activity_buffer)
        time_since_last_activity = (now - last_activity).total_seconds()

        return time_since_last_activity <= IDLE_TIMEOUT_SECONDS

    def _update_active_status(self) -> None:
        """Update and emit active status if changed."""
        new_status = self.is_currently_active()
        if new_status != self._is_active:
            self._is_active = new_status
            self.active_status_changed.emit(new_status)

    @staticmethod
    def _format_duration(total_seconds: int) -> str:
        hours, remainder = divmod(max(0, int(total_seconds)), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
