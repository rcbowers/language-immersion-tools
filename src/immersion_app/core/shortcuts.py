"""Mode-aware keyboard shortcut management."""

from typing import Dict, List
from PySide6.QtGui import QAction
from PySide6.QtCore import QObject

from .mode import WorkspaceMode


class ShortcutGroup:
    """Collection of related keyboard shortcuts."""

    def __init__(self, name: str):
        self.name = name
        self.actions: List[QAction] = []

    def add_action(self, action: QAction):
        self.actions.append(action)

    def set_enabled(self, enabled: bool):
        for action in self.actions:
            action.setEnabled(enabled)


class ShortcutManager(QObject):
    """
    Manages keyboard shortcuts across different workspace modes.

    Groups:
    - global: Always active (Ctrl+O, Ctrl+1/2, Escape, etc.)
    - pdf: Only active in PDF mode (arrows, zoom)
    - video: Only active in video mode (space)
    """

    def __init__(self):
        super().__init__()
        self._groups: Dict[str, ShortcutGroup] = {
            'global': ShortcutGroup('global'),
            'pdf': ShortcutGroup('pdf'),
            'video': ShortcutGroup('video'),
        }

    def add_shortcut(self, group: str, action: QAction):
        if group not in self._groups:
            raise ValueError(f"Unknown shortcut group: {group}")
        self._groups[group].add_action(action)

    def update_for_mode(self, mode: WorkspaceMode):
        """Enable/disable shortcuts based on active mode."""
        self._groups['global'].set_enabled(True)
        self._groups['pdf'].set_enabled(mode == WorkspaceMode.PDF)
        self._groups['video'].set_enabled(mode == WorkspaceMode.VIDEO)
