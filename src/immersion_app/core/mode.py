"""Mode management for PDF and video workspace."""

from enum import Enum, auto
from typing import Optional
from PySide6.QtCore import QObject, Signal


class WorkspaceMode(Enum):
    """Workspace mode enumeration."""
    WELCOME = auto()
    PDF = auto()
    VIDEO = auto()


class ModeManager(QObject):
    """
    Centralized mode state manager.

    Single source of truth for current mode.
    Validates transitions and emits change signals.
    """

    mode_changed = Signal(object)  # WorkspaceMode
    mode_transition_failed = Signal(str, str)  # (mode_name, reason)

    def __init__(self):
        super().__init__()
        self._current_mode = WorkspaceMode.WELCOME
        self._pdf_loaded = False
        self._video_loaded = False

    @property
    def current_mode(self) -> WorkspaceMode:
        return self._current_mode

    def set_mode(self, mode: WorkspaceMode, *, force: bool = False) -> bool:
        """
        Set workspace mode with validation.
        Returns True if successful, False if blocked.
        """
        if mode == self._current_mode:
            return True

        if not force and not self._can_transition_to(mode):
            reason = self._get_transition_failure_reason(mode)
            self.mode_transition_failed.emit(mode.name, reason)
            return False

        self._current_mode = mode
        self.mode_changed.emit(mode)
        return True

    def set_pdf_loaded(self, loaded: bool):
        """Update PDF loaded state."""
        self._pdf_loaded = loaded
        if not loaded and self._current_mode == WorkspaceMode.PDF:
            self.set_mode(WorkspaceMode.WELCOME, force=True)

    def set_video_loaded(self, loaded: bool):
        """Update video loaded state."""
        self._video_loaded = loaded
        if not loaded and self._current_mode == WorkspaceMode.VIDEO:
            self.set_mode(WorkspaceMode.WELCOME, force=True)

    def _can_transition_to(self, mode: WorkspaceMode) -> bool:
        if mode == WorkspaceMode.WELCOME:
            return True
        if mode == WorkspaceMode.PDF:
            return self._pdf_loaded
        if mode == WorkspaceMode.VIDEO:
            return self._video_loaded
        return False

    def _get_transition_failure_reason(self, mode: WorkspaceMode) -> str:
        if mode == WorkspaceMode.PDF and not self._pdf_loaded:
            return "No PDF loaded"
        if mode == WorkspaceMode.VIDEO and not self._video_loaded:
            return "No video loaded"
        return "Unknown reason"

    def mode_string(self) -> str:
        """Get mode as string for backward compatibility."""
        if self._current_mode == WorkspaceMode.PDF:
            return "pdf"
        if self._current_mode == WorkspaceMode.VIDEO:
            return "video"
        return ""
