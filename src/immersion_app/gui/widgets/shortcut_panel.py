"""Floating shortcut panel widget."""

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel

from immersion_app.core.mode import ModeManager, WorkspaceMode
from immersion_app.core.completion_tracker import CompletionTracker
from immersion_app.gui.theme import Theme


class ShortcutPanel(QWidget):
    """
    Floating shortcut panel overlaying right side of main window.

    Provides quick access to common actions:
    - Mark page/video complete
    - Quick add to Anki
    - View queue
    - Toggle dark mode
    """

    page_completed = Signal(str, int, bool)  # (file_path, page, is_checked)
    quick_add_requested = Signal()
    queue_requested = Signal()
    theme_toggle_requested = Signal()

    def __init__(self, mode_manager: ModeManager, completion_tracker: CompletionTracker, parent=None):
        # Frameless tool window (like TranslationPopover)
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.mode_manager = mode_manager
        self.completion_tracker = completion_tracker
        self._current_file_path = ""
        self._current_page = 0
        self._current_mode = WorkspaceMode.WELCOME
        self._is_minimized = False

        self._build_ui()
        self.hide()

    def _build_ui(self):
        """Build the panel UI."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 10)
        self.layout.setSpacing(10)

        # Header with minimize button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.header_label = QLabel("Shortcuts")
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()

        self.minimize_button = QPushButton("−")
        self.minimize_button.setFixedSize(24, 24)
        self.minimize_button.clicked.connect(self.toggle_minimized)
        header_layout.addWidget(self.minimize_button)

        self.layout.addLayout(header_layout)

        # Completion checkbox
        self.completion_checkbox = QCheckBox("Mark page complete")
        self.completion_checkbox.stateChanged.connect(self._on_checkbox_toggled)
        self.layout.addWidget(self.completion_checkbox)

        # Separator line
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background-color: {Theme.BORDER};")
        self.layout.addWidget(separator)

        # Action buttons (vertical stack)
        self.quick_add_button = QPushButton("+ Quick add")
        self.quick_add_button.clicked.connect(self.quick_add_requested.emit)
        self.layout.addWidget(self.quick_add_button)

        self.queue_button = QPushButton("≡ View queue")
        self.queue_button.clicked.connect(self.queue_requested.emit)
        self.layout.addWidget(self.queue_button)

        self.theme_button = QPushButton("◐ Toggle theme")
        self.theme_button.clicked.connect(self.theme_toggle_requested.emit)
        self.layout.addWidget(self.theme_button)

        self.layout.addStretch()

        # Store expanded widgets for minimize animation
        self._expanded_widgets = [
            self.completion_checkbox,
            separator,
            self.quick_add_button,
            self.queue_button,
            self.theme_button,
        ]

    def refresh_theme(self):
        """Apply theme colors to panel."""
        self.setStyleSheet(f"""
            ShortcutPanel {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER_STRONG};
                border-radius: 10px;
            }}
        """)

        self.header_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 14px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
            }}
        """)

        self.minimize_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Theme.TEXT};
                border: none;
                border-radius: 4px;
                padding: 0px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.SURFACE_ALT};
            }}
        """)
        self.completion_checkbox.setStyleSheet(Theme.get_checkbox_style())
        self.quick_add_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.queue_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.theme_button.setStyleSheet(Theme.get_button_style("secondary"))

    def set_current_context(self, file_path: str, page: int, mode: WorkspaceMode):
        """Update panel for current page/video context."""
        self._current_file_path = file_path
        self._current_page = page
        self._current_mode = mode

        # Update checkbox label and visibility based on mode
        if mode == WorkspaceMode.PDF:
            self.completion_checkbox.setText(f"Mark page {page + 1}\ncomplete")
            self.completion_checkbox.setVisible(True)
        else:
            self.completion_checkbox.setVisible(False)

    def update_completion_state(self, is_complete: bool):
        """Update checkbox state from tracker (external state change)."""
        # Block signals to prevent recursion
        self.completion_checkbox.blockSignals(True)
        self.completion_checkbox.setChecked(is_complete)
        self.completion_checkbox.blockSignals(False)

    def _on_checkbox_toggled(self, state):
        """Handle checkbox state change from user interaction."""
        is_checked = state == Qt.CheckState.Checked.value
        self.page_completed.emit(self._current_file_path, self._current_page, is_checked)

        # Animate checkbox on completion
        if is_checked:
            self._animate_completion_check()

    def _animate_completion_check(self):
        """Satisfying scale animation on completion."""
        # Simple opacity pulse (Qt doesn't support CSS animations easily)
        # A more sophisticated approach would use QPropertyAnimation on scale
        pass  # For MVP, skip animation to keep implementation simple

    def toggle_minimized(self):
        """Toggle between expanded and minimized states."""
        self._is_minimized = not self._is_minimized

        if self._is_minimized:
            # Hide expanded widgets
            for widget in self._expanded_widgets:
                widget.hide()
            self.minimize_button.setText("≡")
            # Shrink panel
            self.setFixedSize(50, 50)
        else:
            # Show expanded widgets (skip completion checkbox in video mode)
            for widget in self._expanded_widgets:
                if widget is self.completion_checkbox and self._current_mode == WorkspaceMode.VIDEO:
                    continue
                widget.show()
            self.minimize_button.setText("−")
            # Restore expanded size
            self._resize_to_parent()

        self.position_on_parent()

    def position_on_parent(self):
        """Position panel on right side of parent window."""
        if not self.parent():
            return

        parent = self.parent()
        parent_width = parent.width()
        parent_height = parent.height()

        if self._is_minimized:
            # Small square in center-right
            x = parent_width - 50 - Theme.SHORTCUT_PANEL_MARGIN
            y = (parent_height - 50) // 2
            self.setGeometry(x, y, 50, 50)
        else:
            # Expanded panel - centered vertically
            panel_width = int(parent_width * Theme.SHORTCUT_PANEL_WIDTH_PERCENT)
            panel_height = int(parent_height * Theme.SHORTCUT_PANEL_HEIGHT_PERCENT)

            # Minimum and maximum sizes
            panel_width = max(160, min(panel_width, 240))
            panel_height = max(220, min(panel_height, 350))

            x = parent_width - panel_width - Theme.SHORTCUT_PANEL_MARGIN
            y = (parent_height - panel_height) // 2

            self.setGeometry(x, y, panel_width, panel_height)

    def _resize_to_parent(self):
        """Calculate and set size based on parent dimensions."""
        if not self.parent():
            return

        parent = self.parent()
        panel_width = int(parent.width() * Theme.SHORTCUT_PANEL_WIDTH_PERCENT)
        panel_height = int(parent.height() * Theme.SHORTCUT_PANEL_HEIGHT_PERCENT)

        # Minimum and maximum sizes
        panel_width = max(160, min(panel_width, 240))
        panel_height = max(220, min(panel_height, 350))

        self.setFixedSize(panel_width, panel_height)

    def showEvent(self, event):
        """Handle show event."""
        super().showEvent(event)
        self.position_on_parent()
        self.raise_()
