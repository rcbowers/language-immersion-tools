"""Appearance state management for light and dark themes."""

from enum import Enum

from PySide6.QtCore import QObject, Signal


class AppearanceMode(str, Enum):
    """Supported application appearance modes."""

    LIGHT = "light"
    DARK = "dark"


class AppearanceManager(QObject):
    """Centralized appearance state manager."""

    appearance_changed = Signal(str)

    def __init__(self, initial_mode: str = AppearanceMode.LIGHT.value):
        super().__init__()
        self._current_mode = self.normalize_mode(initial_mode)

    @property
    def current_mode(self) -> AppearanceMode:
        return self._current_mode

    def set_mode(self, mode: str | AppearanceMode) -> bool:
        normalized_mode = self.normalize_mode(mode)
        if normalized_mode == self._current_mode:
            return False
        self._current_mode = normalized_mode
        self.appearance_changed.emit(normalized_mode.value)
        return True

    def mode_string(self) -> str:
        return self._current_mode.value

    @staticmethod
    def normalize_mode(mode: str | AppearanceMode | None) -> AppearanceMode:
        if isinstance(mode, AppearanceMode):
            return mode
        if str(mode or "").strip().lower() == AppearanceMode.DARK.value:
            return AppearanceMode.DARK
        return AppearanceMode.LIGHT
