"""Appearance state management for the app's color themes."""

from enum import Enum

from PySide6.QtCore import QObject, Signal


class AppearanceMode(str, Enum):
    """Supported color themes.

    The value is the persisted ``theme_mode`` id and must match a palette key in
    ``gui/theme.py``. Whether a theme is dark (drives PDF page inversion and
    light/dark toggling) lives here so Core and GUI share one source of truth.
    """

    LIGHT = "light"
    DARK = "dark"
    SEPIA = "sepia"
    FOREST = "forest"
    NORD = "nord"
    SOLARIZED_DARK = "solarized_dark"
    MIDNIGHT = "midnight"

    @property
    def label(self) -> str:
        return _THEME_LABELS[self]

    @property
    def is_dark(self) -> bool:
        return self in _DARK_THEMES


_THEME_LABELS = {
    AppearanceMode.LIGHT: "Light",
    AppearanceMode.DARK: "Dark",
    AppearanceMode.SEPIA: "Sepia",
    AppearanceMode.FOREST: "Forest",
    AppearanceMode.NORD: "Nord",
    AppearanceMode.SOLARIZED_DARK: "Solarized Dark",
    AppearanceMode.MIDNIGHT: "Midnight (OLED)",
}

_DARK_THEMES = frozenset(
    {
        AppearanceMode.DARK,
        AppearanceMode.NORD,
        AppearanceMode.SOLARIZED_DARK,
        AppearanceMode.MIDNIGHT,
    }
)


def available_themes() -> list[tuple[str, str]]:
    """Return ``(theme_id, label)`` pairs in display order."""
    return [(mode.value, mode.label) for mode in AppearanceMode]


class AppearanceManager(QObject):
    """Centralized appearance state manager."""

    appearance_changed = Signal(str)

    def __init__(self, initial_mode: str = AppearanceMode.LIGHT.value):
        super().__init__()
        self._current_mode = self.normalize_mode(initial_mode)

    @property
    def current_mode(self) -> AppearanceMode:
        return self._current_mode

    @property
    def is_dark(self) -> bool:
        return self._current_mode.is_dark

    def set_mode(self, mode: str | AppearanceMode) -> bool:
        normalized_mode = self.normalize_mode(mode)
        if normalized_mode == self._current_mode:
            return False
        self._current_mode = normalized_mode
        self.appearance_changed.emit(normalized_mode.value)
        return True

    def mode_string(self) -> str:
        return self._current_mode.value

    def toggle_mode(self) -> None:
        """Switch between the default light and dark themes.

        From any dark theme this goes to Light; from any light theme to Dark.
        """
        self.set_mode(AppearanceMode.LIGHT if self._current_mode.is_dark else AppearanceMode.DARK)

    @staticmethod
    def normalize_mode(mode: str | AppearanceMode | None) -> AppearanceMode:
        """Coerce any value to a known theme, falling back to Light."""
        if isinstance(mode, AppearanceMode):
            return mode
        text = str(mode or "").strip().lower()
        try:
            return AppearanceMode(text)
        except ValueError:
            return AppearanceMode.LIGHT
