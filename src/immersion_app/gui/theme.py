"""Centralized runtime-switchable theme system for the immersion app."""

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget
import re

from immersion_app.core.appearance_manager import AppearanceManager


class Theme:
    """Modern theme with cool neutrals and electric accent."""

    _PALETTES = {
        "light": {
            "BG": "#fafafa",
            "SURFACE": "#ffffff",
            "SURFACE_ALT": "#f4f4f5",
            "SURFACE_OVERLAY": "rgba(255, 255, 255, 0.95)",
            "TOAST_BG": "rgba(255, 255, 255, 0.97)",
            "BORDER": "rgba(0,0,0,0.07)",
            "BORDER_STRONG": "rgba(0,0,0,0.12)",
            "TEXT": "#18181b",
            "TEXT_SOFT": "#52525b",
            "TEXT_MUTED": "#a1a1aa",
            "ACCENT": "#5b6cff",
            "ACCENT_DARK": "#2f3fd9",
            "ACCENT_SOFT": "rgba(91,108,255,0.10)",
            "ACCENT_BORDER": "rgba(91,108,255,0.25)",
            "ACCENT_HOVER": "#4a5ce6",
            "ACCENT_PRESSED": "#3d4ed9",
            "ACCENT_TEXT": "#ffffff",
            "HL_SEEN": "rgba(91,108,255,0.10)",
            "HL_NEW": "rgba(91,108,255,0.0)",
            "HL_SELECTED": "rgba(91,108,255,0.35)",
            "SUCCESS": "#16a34a",
            "WARNING": "#b45309",
            "DANGER": "#dc2626",
        },
        "dark": {
            "BG": "#111318",
            "SURFACE": "#181b22",
            "SURFACE_ALT": "#222733",
            "SURFACE_OVERLAY": "rgba(24, 27, 34, 0.96)",
            "TOAST_BG": "rgba(24, 27, 34, 0.98)",
            "BORDER": "rgba(255,255,255,0.10)",
            "BORDER_STRONG": "rgba(255,255,255,0.18)",
            "TEXT": "#f3f4f6",
            "TEXT_SOFT": "#c3cad5",
            "TEXT_MUTED": "#8d97a8",
            "ACCENT": "#7c8cff",
            "ACCENT_DARK": "#b5c0ff",
            "ACCENT_SOFT": "rgba(124,140,255,0.18)",
            "ACCENT_BORDER": "rgba(124,140,255,0.35)",
            "ACCENT_HOVER": "#4a5ce6",
            "ACCENT_PRESSED": "#3d4ed9",
            "ACCENT_TEXT": "#ffffff",
            "HL_SEEN": "rgba(124,140,255,0.18)",
            "HL_NEW": "rgba(124,140,255,0.03)",
            "HL_SELECTED": "rgba(124,140,255,0.38)",
            "SUCCESS": "#4ade80",
            "WARNING": "#fbbf24",
            "DANGER": "#f87171",
        },
        "sepia": {
            "BG": "#f4ecd8",
            "SURFACE": "#fbf6e9",
            "SURFACE_ALT": "#ece2c8",
            "SURFACE_OVERLAY": "rgba(251, 246, 233, 0.95)",
            "TOAST_BG": "rgba(251, 246, 233, 0.97)",
            "BORDER": "rgba(59,50,38,0.12)",
            "BORDER_STRONG": "rgba(59,50,38,0.2)",
            "TEXT": "#3b3226",
            "TEXT_SOFT": "#6b5d49",
            "TEXT_MUTED": "#9a8b72",
            "ACCENT": "#9a5b2e",
            "ACCENT_DARK": "#6f3f1a",
            "ACCENT_SOFT": "rgba(154,91,46,0.1)",
            "ACCENT_BORDER": "rgba(154,91,46,0.25)",
            "ACCENT_HOVER": "#874f27",
            "ACCENT_PRESSED": "#754421",
            "ACCENT_TEXT": "#ffffff",
            "HL_SEEN": "rgba(154,91,46,0.1)",
            "HL_NEW": "rgba(154,91,46,0.0)",
            "HL_SELECTED": "rgba(154,91,46,0.35)",
            "SUCCESS": "#3f7d3a",
            "WARNING": "#a16207",
            "DANGER": "#b91c1c",
        },
        "forest": {
            "BG": "#f1f5ef",
            "SURFACE": "#fbfdf9",
            "SURFACE_ALT": "#e6ede2",
            "SURFACE_OVERLAY": "rgba(251, 253, 249, 0.95)",
            "TOAST_BG": "rgba(251, 253, 249, 0.97)",
            "BORDER": "rgba(31,45,36,0.1)",
            "BORDER_STRONG": "rgba(31,45,36,0.16)",
            "TEXT": "#1f2d24",
            "TEXT_SOFT": "#4a5d51",
            "TEXT_MUTED": "#8a9c8f",
            "ACCENT": "#2f7d5b",
            "ACCENT_DARK": "#1d5a40",
            "ACCENT_SOFT": "rgba(47,125,91,0.1)",
            "ACCENT_BORDER": "rgba(47,125,91,0.25)",
            "ACCENT_HOVER": "#29704f",
            "ACCENT_PRESSED": "#236143",
            "ACCENT_TEXT": "#ffffff",
            "HL_SEEN": "rgba(47,125,91,0.1)",
            "HL_NEW": "rgba(47,125,91,0.0)",
            "HL_SELECTED": "rgba(47,125,91,0.35)",
            "SUCCESS": "#0d9488",
            "WARNING": "#b45309",
            "DANGER": "#dc2626",
        },
        "nord": {
            "BG": "#2e3440",
            "SURFACE": "#3b4252",
            "SURFACE_ALT": "#434c5e",
            "SURFACE_OVERLAY": "rgba(59, 66, 82, 0.96)",
            "TOAST_BG": "rgba(59, 66, 82, 0.98)",
            "BORDER": "rgba(255,255,255,0.1)",
            "BORDER_STRONG": "rgba(255,255,255,0.18)",
            "TEXT": "#eceff4",
            "TEXT_SOFT": "#d8dee9",
            "TEXT_MUTED": "#9aa5ba",
            "ACCENT": "#88c0d0",
            "ACCENT_DARK": "#b0dbe6",
            "ACCENT_SOFT": "rgba(136,192,208,0.18)",
            "ACCENT_BORDER": "rgba(136,192,208,0.35)",
            "ACCENT_HOVER": "#7ab3c3",
            "ACCENT_PRESSED": "#6ba5b5",
            "ACCENT_TEXT": "#2e3440",
            "HL_SEEN": "rgba(136,192,208,0.18)",
            "HL_NEW": "rgba(136,192,208,0.03)",
            "HL_SELECTED": "rgba(136,192,208,0.38)",
            "SUCCESS": "#a3be8c",
            "WARNING": "#ebcb8b",
            "DANGER": "#d9737d",
        },
        "solarized_dark": {
            "BG": "#002b36",
            "SURFACE": "#073642",
            "SURFACE_ALT": "#0d4452",
            "SURFACE_OVERLAY": "rgba(7, 54, 66, 0.96)",
            "TOAST_BG": "rgba(7, 54, 66, 0.98)",
            "BORDER": "rgba(255,255,255,0.1)",
            "BORDER_STRONG": "rgba(255,255,255,0.18)",
            "TEXT": "#93a1a1",
            "TEXT_SOFT": "#839496",
            "TEXT_MUTED": "#657b83",
            "ACCENT": "#4aa3e3",
            "ACCENT_DARK": "#8cc8f0",
            "ACCENT_SOFT": "rgba(74,163,227,0.18)",
            "ACCENT_BORDER": "rgba(74,163,227,0.35)",
            "ACCENT_HOVER": "#3b94d4",
            "ACCENT_PRESSED": "#2f85c4",
            "ACCENT_TEXT": "#002b36",
            "HL_SEEN": "rgba(74,163,227,0.18)",
            "HL_NEW": "rgba(74,163,227,0.03)",
            "HL_SELECTED": "rgba(74,163,227,0.38)",
            "SUCCESS": "#9aae00",
            "WARNING": "#d4a017",
            "DANGER": "#f0544f",
        },
        "midnight": {
            "BG": "#000000",
            "SURFACE": "#0b0b0f",
            "SURFACE_ALT": "#17171d",
            "SURFACE_OVERLAY": "rgba(11, 11, 15, 0.96)",
            "TOAST_BG": "rgba(11, 11, 15, 0.98)",
            "BORDER": "rgba(255,255,255,0.1)",
            "BORDER_STRONG": "rgba(255,255,255,0.18)",
            "TEXT": "#e6e6ea",
            "TEXT_SOFT": "#b4b4bd",
            "TEXT_MUTED": "#7c7c88",
            "ACCENT": "#ff7a59",
            "ACCENT_DARK": "#ffb199",
            "ACCENT_SOFT": "rgba(255,122,89,0.18)",
            "ACCENT_BORDER": "rgba(255,122,89,0.35)",
            "ACCENT_HOVER": "#f06a48",
            "ACCENT_PRESSED": "#de5c3b",
            "ACCENT_TEXT": "#1a0c08",
            "HL_SEEN": "rgba(255,122,89,0.18)",
            "HL_NEW": "rgba(255,122,89,0.03)",
            "HL_SELECTED": "rgba(255,122,89,0.38)",
            "SUCCESS": "#4ade80",
            "WARNING": "#fbbf24",
            "DANGER": "#f87171",
        },
    }

    _mode = "light"

    # Base Colors
    BG = ""
    SURFACE = ""
    SURFACE_ALT = ""
    SURFACE_OVERLAY = ""
    TOAST_BG = ""
    BORDER = ""
    BORDER_STRONG = ""

    # Text Colors
    TEXT = ""
    TEXT_SOFT = ""
    TEXT_MUTED = ""

    # Accent Colors
    ACCENT = ""
    ACCENT_DARK = ""
    ACCENT_SOFT = ""
    ACCENT_BORDER = ""
    ACCENT_HOVER = ""
    ACCENT_PRESSED = ""
    ACCENT_TEXT = ""

    # Word Highlight States
    HL_SEEN = ""
    HL_NEW = ""
    HL_SELECTED = ""

    # Status Colors
    SUCCESS = ""
    WARNING = ""
    DANGER = ""

    # Dialog layout
    DIALOG_MARGIN = 20
    DIALOG_SPACING = 12
    SETTINGS_DIALOG_WIDTH = 560

    # Typography
    FONT_FAMILY = "Inter"
    FONT_FALLBACK = "Segoe UI, system-ui, -apple-system, sans-serif"
    FONT_MONO = "JetBrains Mono, Consolas, monospace"

    # Font Sizes
    FONT_SIZE_BODY = "14.5px"
    FONT_SIZE_TITLE = "26px"
    FONT_SIZE_HEADING = "19px"
    FONT_SIZE_SUBHEAD = "12.5px"
    FONT_SIZE_CAPTION = "11px"
    FONT_SIZE_MICRO = "9px"

    # Font Weights
    FONT_WEIGHT_REGULAR = 400
    FONT_WEIGHT_MEDIUM = 500
    FONT_WEIGHT_SEMIBOLD = 600
    FONT_WEIGHT_BOLD = 700

    # Spacing
    COMMAND_BAR_HEIGHT = 44
    TRANSPORT_BAR_HEIGHT = 38
    STATUS_BAR_HEIGHT = 28
    CHAPTER_RAIL_WIDTH = 48
    POPOVER_WIDTH = 320

    # Shortcut Panel
    SHORTCUT_PANEL_WIDTH_PERCENT = 0.10  # 10% of window width
    SHORTCUT_PANEL_HEIGHT_PERCENT = 0.20  # 20% of window height
    SHORTCUT_PANEL_MARGIN = 16  # Margin from edges

    @classmethod
    def apply_mode(cls, mode: str) -> None:
        """Activate the requested palette (unknown ids fall back to light)."""
        theme = AppearanceManager.normalize_mode(mode)
        palette = cls._PALETTES[theme.value]
        cls._mode = theme.value
        for token_name, token_value in palette.items():
            setattr(cls, token_name, token_value)

    @classmethod
    def current_mode(cls) -> str:
        return cls._mode

    @classmethod
    def is_dark(cls) -> bool:
        return AppearanceManager.normalize_mode(cls._mode).is_dark

    @staticmethod
    def to_qcolor(color_string: str) -> QColor:
        """
        Convert color string (hex or rgba) to QColor.

        Args:
            color_string: Color in format "#rrggbb" or "rgba(r,g,b,a)"

        Returns:
            QColor object
        """
        if color_string.startswith('#'):
            return QColor(color_string)
        elif color_string.startswith('rgba'):
            # Parse rgba(r,g,b,a) format
            match = re.match(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)', color_string)
            if match:
                r, g, b, a = match.groups()
                color = QColor(int(r), int(g), int(b))
                color.setAlphaF(float(a))
                return color

        # Fallback
        return QColor(color_string)

    @staticmethod
    def apply_command_bar_style(widget: QWidget) -> None:
        """Apply command bar styling to a widget.

        The selector is scoped to the bar's object name: a bare ``QWidget``
        selector cascades to every child label, giving each its own
        background box and bottom border.
        """
        from PySide6.QtCore import Qt

        if not widget.objectName():
            widget.setObjectName("CommandBar")
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        name = widget.objectName()
        widget.setStyleSheet(f"""
            #{name} {{
                background-color: {Theme.SURFACE};
                border-bottom: 1px solid {Theme.BORDER};
            }}
            #{name} QLabel {{
                background-color: transparent;
                border: none;
            }}
        """)

    @staticmethod
    def get_button_style(variant: str = "primary") -> str:
        """
        Get stylesheet for button variants.

        Args:
            variant: "primary", "secondary", or "ghost"

        Returns:
            CSS stylesheet string
        """
        if variant == "primary":
            return f"""
                QPushButton {{
                    background-color: {Theme.ACCENT};
                    color: {Theme.ACCENT_TEXT};
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: 13px;
                    font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                }}
                QPushButton:hover {{
                    background-color: {Theme.ACCENT_HOVER};
                }}
                QPushButton:pressed {{
                    background-color: {Theme.ACCENT_PRESSED};
                }}
                QPushButton:disabled {{
                    background-color: {Theme.SURFACE_ALT};
                    color: {Theme.TEXT_MUTED};
                }}
            """
        elif variant == "secondary":
            return f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Theme.TEXT};
                    border: 1px solid {Theme.BORDER_STRONG};
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: 13px;
                    font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                }}
                QPushButton:hover {{
                    background-color: {Theme.SURFACE_ALT};
                }}
                QPushButton:pressed {{
                    background-color: {Theme.BORDER_STRONG};
                }}
            """
        elif variant == "ghost":
            return f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Theme.TEXT_SOFT};
                    border: none;
                    border-radius: 6px;
                    padding: 8px;
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: {Theme.SURFACE_ALT};
                }}
                QPushButton:pressed {{
                    background-color: {Theme.BORDER_STRONG};
                }}
            """
        elif variant == "compact_accent":
            return f"""
                QPushButton {{
                    background-color: {Theme.ACCENT};
                    color: {Theme.ACCENT_TEXT};
                    border: none;
                    border-radius: 6px;
                    padding: 0px;
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: 16px;
                    font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
                }}
                QPushButton:hover {{
                    background-color: {Theme.ACCENT_HOVER};
                }}
                QPushButton:pressed {{
                    background-color: {Theme.ACCENT_PRESSED};
                }}
                QPushButton:disabled {{
                    background-color: {Theme.SURFACE_ALT};
                    color: {Theme.TEXT_MUTED};
                }}
            """

        return ""

    @staticmethod
    def get_checkbox_style() -> str:
        """Styled checkbox for completion tracking."""
        return f"""
            QCheckBox {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border: 2px solid {Theme.BORDER_STRONG};
                border-radius: 4px;
                background-color: {Theme.SURFACE_ALT};
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.ACCENT};
                border-color: {Theme.ACCENT};
            }}
            QCheckBox::indicator:hover {{
                border-color: {Theme.ACCENT};
            }}
        """

    @staticmethod
    def get_combo_style() -> str:
        """Stylesheet for combo boxes (editable or not)."""
        return f"""
            QComboBox {{
                background-color: {Theme.SURFACE_ALT};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 5px 10px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
                min-height: 20px;
            }}
            QComboBox:focus {{
                border: 1px solid {Theme.ACCENT_BORDER};
            }}
            QComboBox QAbstractItemView {{
                background-color: {Theme.SURFACE};
                color: {Theme.TEXT};
                selection-background-color: {Theme.ACCENT_SOFT};
                selection-color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER_STRONG};
            }}
        """

    @staticmethod
    def get_dialog_style() -> str:
        """Base stylesheet for dialogs: background, group boxes and form labels."""
        return f"""
            QDialog {{
                background-color: {Theme.BG};
            }}
            QGroupBox {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
                border: 1px solid {Theme.BORDER};
                border-radius: 8px;
                margin-top: 14px;
                padding: 12px 10px 8px 10px;
                background-color: {Theme.SURFACE};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }}
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
            }}
            QCheckBox {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
            }}
        """

    @staticmethod
    def get_status_text_style(state: str) -> str:
        """Label style for an inline status message. ``state``: "ok", "warning", "error" or "muted"."""
        color = {
            "ok": Theme.SUCCESS,
            "warning": Theme.WARNING,
            "error": Theme.DANGER,
        }.get(state, Theme.TEXT_MUTED)
        return f"""
            QLabel {{
                color: {color};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12.5px;
            }}
        """

    @staticmethod
    def get_menu_style() -> str:
        """Get stylesheet for menus and submenus."""
        return f"""
            QMenu {{
                background-color: {Theme.SURFACE};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                background-color: transparent;
                color: {Theme.TEXT};
                padding: 8px 12px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {Theme.SURFACE_ALT};
            }}
            QMenu::item:disabled {{
                color: {Theme.TEXT_MUTED};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {Theme.BORDER};
                margin: 4px 0px;
            }}
        """

    @staticmethod
    def get_input_style() -> str:
        """Get stylesheet for input fields."""
        return f"""
            QLineEdit {{
                background-color: {Theme.SURFACE_ALT};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 6px 12px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.ACCENT_BORDER};
                background-color: {Theme.SURFACE};
            }}
        """

    @staticmethod
    def get_label_style(variant: str = "body") -> str:
        """
        Get stylesheet for label variants.

        Args:
            variant: "body", "heading", "caption", "muted"

        Returns:
            CSS stylesheet string
        """
        if variant == "heading":
            return f"""
                QLabel {{
                    color: {Theme.TEXT};
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: {Theme.FONT_SIZE_HEADING};
                    font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
                }}
            """
        elif variant == "caption":
            return f"""
                QLabel {{
                    color: {Theme.TEXT_SOFT};
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: {Theme.FONT_SIZE_CAPTION};
                    font-weight: {Theme.FONT_WEIGHT_REGULAR};
                }}
            """
        elif variant == "muted":
            return f"""
                QLabel {{
                    color: {Theme.TEXT_MUTED};
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: {Theme.FONT_SIZE_CAPTION};
                    font-weight: {Theme.FONT_WEIGHT_REGULAR};
                }}
            """
        else:  # body
            return f"""
                QLabel {{
                    color: {Theme.TEXT};
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: {Theme.FONT_SIZE_BODY};
                    font-weight: {Theme.FONT_WEIGHT_REGULAR};
                }}
            """

    @staticmethod
    def get_scrollbar_style(orientation: str = "vertical") -> str:
        """
        Get stylesheet for custom scrollbar styling.

        Args:
            orientation: "vertical", "horizontal", or "both"

        Returns:
            CSS stylesheet string
        """
        if orientation not in {"vertical", "horizontal", "both"}:
            raise ValueError("orientation must be 'vertical', 'horizontal', or 'both'")

        vertical_style = f"""
            QScrollBar:vertical {{
                background-color: transparent;
                width: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {Theme.TEXT_MUTED};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {Theme.TEXT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """

        horizontal_style = f"""
            QScrollBar:horizontal {{
                background-color: transparent;
                height: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {Theme.TEXT_MUTED};
                border-radius: 4px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {Theme.TEXT};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """

        if orientation == "vertical":
            return vertical_style
        if orientation == "horizontal":
            return horizontal_style
        return f"{vertical_style}\n{horizontal_style}"


Theme.apply_mode("light")
