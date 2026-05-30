"""State manager for usage time tracking."""

from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from immersion_app.core.user_data import save_user_data


class UsageTimeTracker(QObject):
    """
    Manages usage time tracking.

    Single source of truth for tracking active usage time when the app is focused.
    Follows the pattern from CompletionTracker.
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

        # Inactivity timer (checks every 30 seconds)
        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.timeout.connect(self._check_inactivity)
        self._inactivity_timer.start(30000)  # 30 seconds

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
        # Finalize previous session if exists
        if self._session_start_time is not None:
            self.finalize_current_session()

        # Start new session
        self._current_file_path = self._normalize_path(file_path)
        self._current_file_type = "pdf"
        self._session_start_time = datetime.now()
        self._session_start_location = "Page 1"
        self._current_location = "Page 1"
        self._start_page_index = 0
        self._current_page_index = 0
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
        # Finalize previous session if exists
        if self._session_start_time is not None:
            self.finalize_current_session()

        # Start new session
        self._current_file_path = self._normalize_path(file_path)
        self._current_file_type = "video"
        self._session_start_time = datetime.now()
        self._session_start_location = "00:00:00"
        self._current_location = "00:00:00"
        self._start_page_index = None
        self._current_page_index = None
        self._start_position_ms = 0
        self._current_position_ms = 0
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
        """Record user activity (only if window is focused)."""
        if not self._is_window_focused:
            return

        if self._session_start_time is None:
            return

        now = datetime.now()
        self._activity_buffer.append(now)

        # Update last activity timestamp in user data (for potential crash recovery)
        self._user_data["usage_time"]["last_activity_timestamp"] = now.isoformat()

        # Update active status
        self._update_active_status()

    def finalize_current_session(self) -> None:
        """Calculate duration and save completed session to user_data."""
        if self._session_start_time is None:
            return

        if not self._activity_buffer:
            # No activity recorded, don't save session
            self._reset_session_state()
            return

        # Calculate duration by merging 2-minute activity windows
        duration_seconds = self._calculate_session_duration()

        if duration_seconds <= 0:
            self._reset_session_state()
            return

        session_end_time = datetime.now()
        elapsed_seconds = max(
            duration_seconds,
            max(0, int((session_end_time - self._session_start_time).total_seconds())),
        )
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

        session_record = {
            "file_path": self._current_file_path,
            "file_type": self._current_file_type,
            "start_time": self._session_start_time.isoformat(),
            "end_time": session_end_time.isoformat(),
            "duration_seconds": duration_seconds,
            "elapsed_seconds": elapsed_seconds,
            "metadata": metadata,
        }

        # Save to user data
        self._user_data["usage_time"]["sessions"].append(session_record)
        self._user_data["usage_time"]["total_seconds"] += duration_seconds
        self._user_data["usage_time"]["last_activity_timestamp"] = session_end_time.isoformat()

        save_user_data(self._user_data)

        # Emit signals
        self.session_ended.emit(self._current_file_path, duration_seconds)
        self.stats_updated.emit(
            self.get_today_usage_seconds(),
            self.get_total_usage_seconds()
        )

        self._reset_session_state()

    def _reset_session_state(self) -> None:
        """Clear in-memory session state."""
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

    def _calculate_session_duration(self) -> int:
        """
        Calculate total active duration by merging overlapping 2-minute windows.

        Each activity timestamp creates a 2-minute window (±1 minute).
        Overlapping windows are merged, and the total duration is the sum of merged ranges.
        """
        if not self._activity_buffer:
            return 0

        # Create 2-minute windows around each activity (±1 minute = ±60 seconds)
        WINDOW_HALF_SIZE = 60  # seconds

        # Sort activities by timestamp
        sorted_activities = sorted(self._activity_buffer)

        # Convert to time windows (start, end) in seconds since epoch
        windows = []
        for activity_time in sorted_activities:
            timestamp = activity_time.timestamp()
            window_start = timestamp - WINDOW_HALF_SIZE
            window_end = timestamp + WINDOW_HALF_SIZE
            windows.append((window_start, window_end))

        # Merge overlapping windows
        merged_windows = []
        for start, end in windows:
            if not merged_windows:
                merged_windows.append([start, end])
            else:
                last_start, last_end = merged_windows[-1]
                if start <= last_end:
                    # Overlapping, extend the last window
                    merged_windows[-1][1] = max(last_end, end)
                else:
                    # Non-overlapping, add new window
                    merged_windows.append([start, end])

        # Sum up the durations
        total_seconds = sum(end - start for start, end in merged_windows)
        return int(total_seconds)

    def _check_inactivity(self) -> None:
        """Check for inactivity and finalize session if >2 minutes idle."""
        # Update active status (this will check if still active)
        self._update_active_status()

        if self._session_start_time is None:
            return

        if not self._activity_buffer:
            return

        now = datetime.now()
        last_activity = max(self._activity_buffer)
        time_since_last_activity = (now - last_activity).total_seconds()

        # If inactive for more than 2 minutes, finalize session
        if time_since_last_activity > 120:  # 2 minutes
            self.finalize_current_session()

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
        - Recent activity within last 2 minutes
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

        return time_since_last_activity <= 120  # 2 minutes

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
