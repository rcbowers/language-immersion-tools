"""Core services and shared models.

Imports are lazy so command-line utilities can use pure core modules without
loading Qt-backed state managers.
"""

from importlib import import_module

__all__ = [
    'ActivityAnalyticsManager',
    'WorkspaceMode',
    'ModeManager',
    'SelectionState',
    'PdfSelectionState',
    'VideoSelectionState',
    'ShortcutManager',
]


_EXPORTS = {
    'ActivityAnalyticsManager': ('.activity_analytics', 'ActivityAnalyticsManager'),
    'WorkspaceMode': ('.mode', 'WorkspaceMode'),
    'ModeManager': ('.mode', 'ModeManager'),
    'SelectionState': ('.selection_state', 'SelectionState'),
    'PdfSelectionState': ('.selection_state', 'PdfSelectionState'),
    'VideoSelectionState': ('.selection_state', 'VideoSelectionState'),
    'ShortcutManager': ('.shortcuts', 'ShortcutManager'),
}


def __getattr__(name):
    """Load public Qt-backed services only when a caller requests one."""
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value

