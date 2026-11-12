"""State manager for content browser library (imported PDFs and videos)."""

from __future__ import annotations

import os
import hashlib
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, Signal

from immersion_app.core.user_data import save_user_data


class ContentBrowserManager(QObject):
    """
    Manages the content browser library state.

    Single source of truth for imported content (PDFs and videos).
    Follows the pattern from CompletionTracker.
    """

    content_added = Signal(dict)  # Emits content item dict
    content_removed = Signal(str)  # Emits file path
    content_updated = Signal(dict)  # Emits updated content item dict

    def __init__(self, user_data: dict):
        super().__init__()
        self._user_data = user_data
        self._ensure_content_section()

    def _ensure_content_section(self) -> dict:
        """Ensure imported_content section exists in user data."""
        if "imported_content" not in self._user_data:
            self._user_data["imported_content"] = {"items": []}
        elif not isinstance(self._user_data["imported_content"], dict):
            self._user_data["imported_content"] = {"items": []}
        elif "items" not in self._user_data["imported_content"]:
            self._user_data["imported_content"]["items"] = []
        elif not isinstance(self._user_data["imported_content"]["items"], list):
            self._user_data["imported_content"]["items"] = []

        return self._user_data["imported_content"]

    def _normalize_path(self, file_path: str) -> str:
        """Normalize file path for consistent storage (Windows-compatible)."""
        return os.path.normcase(os.path.abspath(file_path))

    def _generate_preview_hash(self, file_path: str) -> str:
        """Generate deterministic hash for preview cache lookup."""
        normalized = self._normalize_path(file_path)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:8]

    def get_all_content(self) -> list[dict]:
        """Get all imported content items."""
        content_section = self._ensure_content_section()
        return content_section["items"]

    def get_content_by_path(self, file_path: str) -> Optional[dict]:
        """Get content item by file path."""
        normalized_path = self._normalize_path(file_path)
        for item in self.get_all_content():
            if self._normalize_path(item.get("path", "")) == normalized_path:
                return item
        return None

    def add_content(
        self,
        file_path: str,
        content_type: str,
        page_count: Optional[int] = None,
        duration_ms: Optional[int] = None,
        last_position: Optional[dict] = None
    ) -> dict:
        """
        Add or update content in the library.

        Args:
            file_path: Absolute path to content file
            content_type: "pdf", "epub" or "video"
            page_count: Total pages for PDFs
            duration_ms: Duration in milliseconds for videos
            last_position: Dict with "page_index" (PDF) or "video_position_ms" (video)

        Returns:
            The content item dict (created or updated)
        """
        normalized_path = self._normalize_path(file_path)

        # Check if already exists
        existing = self.get_content_by_path(file_path)

        if existing:
            # Update existing item
            if page_count is not None:
                existing["page_count"] = page_count
            if duration_ms is not None:
                existing["duration_ms"] = duration_ms
            if last_position is not None:
                existing["last_position"] = last_position

            save_user_data(self._user_data)
            self.content_updated.emit(existing)
            return existing

        # Create new item
        item = {
            "path": normalized_path,
            "type": content_type,
            "name": os.path.basename(file_path),
            "added_at": datetime.now().isoformat(),
            "preview_hash": self._generate_preview_hash(file_path)
        }

        if page_count is not None:
            item["page_count"] = page_count
        if duration_ms is not None:
            item["duration_ms"] = duration_ms
        if last_position is not None:
            item["last_position"] = last_position

        content_section = self._ensure_content_section()
        content_section["items"].append(item)

        save_user_data(self._user_data)
        self.content_added.emit(item)

        return item

    def remove_content(self, file_path: str) -> bool:
        """
        Remove content from the library.

        Returns:
            True if content was removed, False if not found
        """
        normalized_path = self._normalize_path(file_path)
        content_section = self._ensure_content_section()

        original_length = len(content_section["items"])
        content_section["items"] = [
            item for item in content_section["items"]
            if self._normalize_path(item.get("path", "")) != normalized_path
        ]

        if len(content_section["items"]) != original_length:
            save_user_data(self._user_data)
            self.content_removed.emit(file_path)
            return True

        return False

    def update_last_position(self, file_path: str, last_position: dict) -> None:
        """Update the last position for a content item."""
        existing = self.get_content_by_path(file_path)
        if existing:
            existing["last_position"] = last_position
            save_user_data(self._user_data)
            self.content_updated.emit(existing)

    def content_exists(self, file_path: str) -> bool:
        """Check if content is in the library."""
        return self.get_content_by_path(file_path) is not None
