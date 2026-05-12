"""State manager for content completion tracking (pages, videos)."""

from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from immersion_app.core.user_data import save_user_data


class CompletionTracker(QObject):
    """
    Manages content completion state.

    Single source of truth for page and video completion tracking.
    Follows the pattern from AnkiAnalyticsManager.
    """

    completion_changed = Signal(str, int, bool)  # (file_path, page, is_complete)

    def __init__(self, user_data: dict):
        super().__init__()
        self._user_data = user_data
        self._ensure_progress_section()

    def _ensure_progress_section(self) -> dict:
        """Ensure progress section exists in user data."""
        progress = self._user_data.setdefault("progress", {})
        completed_pages = progress.get("completed_pages")
        progress["completed_pages"] = completed_pages if isinstance(completed_pages, dict) else {}
        completed_videos = progress.get("completed_videos")
        progress["completed_videos"] = completed_videos if isinstance(completed_videos, dict) else {}
        return progress

    def _normalize_path(self, file_path: str) -> str:
        """Normalize file path for consistent storage (Windows-compatible)."""
        return os.path.normcase(os.path.abspath(file_path))

    def is_page_complete(self, file_path: str, page_index: int) -> bool:
        """Query completion state for a specific page."""
        normalized_path = self._normalize_path(file_path)
        completed_pages = self._user_data["progress"]["completed_pages"].get(normalized_path, [])
        return any(entry.get("page") == page_index for entry in completed_pages)

    def mark_page_complete(self, file_path: str, page_index: int) -> None:
        """Mark page complete, emit signal, and save."""
        normalized_path = self._normalize_path(file_path)
        completed_pages = self._user_data["progress"]["completed_pages"]

        # Get or create page list for this file
        if normalized_path not in completed_pages:
            completed_pages[normalized_path] = []

        page_list = completed_pages[normalized_path]

        # Check if already completed (prevent duplicates)
        if any(entry.get("page") == page_index for entry in page_list):
            return

        # Add completion entry
        page_list.append({
            "page": page_index,
            "completed_at": datetime.now().isoformat()
        })

        # Sort by page number for cleaner data
        page_list.sort(key=lambda x: x.get("page", 0))

        # Save and emit
        save_user_data(self._user_data)
        self.completion_changed.emit(file_path, page_index, True)

    def unmark_page_complete(self, file_path: str, page_index: int) -> None:
        """Toggle off completion (remove from completed pages)."""
        normalized_path = self._normalize_path(file_path)
        completed_pages = self._user_data["progress"]["completed_pages"]

        if normalized_path not in completed_pages:
            return

        page_list = completed_pages[normalized_path]

        # Remove the page entry if it exists
        original_length = len(page_list)
        completed_pages[normalized_path] = [
            entry for entry in page_list if entry.get("page") != page_index
        ]

        # Only save and emit if something changed
        if len(completed_pages[normalized_path]) != original_length:
            # Clean up empty lists
            if not completed_pages[normalized_path]:
                del completed_pages[normalized_path]

            save_user_data(self._user_data)
            self.completion_changed.emit(file_path, page_index, False)

    def get_completed_pages(self, file_path: str) -> list[int]:
        """Get all completed page numbers for a file."""
        normalized_path = self._normalize_path(file_path)
        completed_pages = self._user_data["progress"]["completed_pages"].get(normalized_path, [])
        return sorted([entry.get("page", -1) for entry in completed_pages if entry.get("page") is not None])

    def get_completion_percentage(self, file_path: str, total_pages: int) -> float:
        """Calculate completion percentage for a file."""
        if total_pages <= 0:
            return 0.0

        completed_pages = self.get_completed_pages(file_path)
        return (len(completed_pages) / total_pages) * 100.0

    def is_video_complete(self, file_path: str) -> bool:
        """Query video completion state."""
        normalized_path = self._normalize_path(file_path)
        return normalized_path in self._user_data["progress"]["completed_videos"]

    def mark_video_complete(self, file_path: str) -> None:
        """Mark entire video complete."""
        normalized_path = self._normalize_path(file_path)
        completed_videos = self._user_data["progress"]["completed_videos"]

        # Check if already completed
        if normalized_path in completed_videos:
            return

        # Add completion entry
        completed_videos[normalized_path] = {
            "completed_at": datetime.now().isoformat()
        }

        # Save (no signal emission for videos yet, can add if needed)
        save_user_data(self._user_data)

    def unmark_video_complete(self, file_path: str) -> None:
        """Toggle off video completion."""
        normalized_path = self._normalize_path(file_path)
        completed_videos = self._user_data["progress"]["completed_videos"]

        if normalized_path in completed_videos:
            del completed_videos[normalized_path]
            save_user_data(self._user_data)
