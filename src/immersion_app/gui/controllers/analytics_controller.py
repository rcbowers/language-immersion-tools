from __future__ import annotations

from immersion_app.gui.widgets.activity_analytics_dialog import ActivityAnalyticsDialog


class AnalyticsController:
    """Orchestrates the activity analytics dialog."""

    def __init__(self, window, analytics_manager):
        self.window = window
        self.analytics_manager = analytics_manager
        self._dialog: ActivityAnalyticsDialog | None = None
        self.analytics_manager.stats_changed.connect(self._refresh_dialog_if_visible)

    def show_dialog(self) -> None:
        if self._dialog is None:
            self._dialog = ActivityAnalyticsDialog(self.window)
        self._dialog.refresh_theme()
        self._dialog.render_snapshot(self.analytics_manager.get_dashboard_data())
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    def refresh(self) -> None:
        self.analytics_manager.refresh()

    def _refresh_dialog_if_visible(self) -> None:
        if self._dialog is None:
            return
        self._dialog.refresh_theme()
        self._dialog.render_snapshot(self.analytics_manager.get_dashboard_data())
