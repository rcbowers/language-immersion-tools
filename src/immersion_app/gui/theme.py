"""
Centralized theme system for the immersion app.

Defines all color tokens, typography constants, and styling helpers
for the modern Arc/Linear-inspired interface.
"""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget
import re


class Theme:
    """Modern theme with cool neutrals and electric accent."""

    # Base Colors
    BG = "#fafafa"
    SURFACE = "#ffffff"
    SURFACE_ALT = "#f4f4f5"
    BORDER = "rgba(0,0,0,0.07)"
    BORDER_STRONG = "rgba(0,0,0,0.12)"

    # Text Colors
    TEXT = "#18181b"
    TEXT_SOFT = "#52525b"
    TEXT_MUTED = "#a1a1aa"

    # Accent Colors
    ACCENT = "#5b6cff"
    ACCENT_SOFT = "rgba(91,108,255,0.10)"
    ACCENT_BORDER = "rgba(91,108,255,0.25)"

    # Word Highlight States
    HL_SEEN = "rgba(91,108,255,0.10)"    # Previously added to Anki
    HL_NEW = "rgba(91,108,255,0.0)"     # Never seen before
    HL_SELECTED = "rgba(91,108,255,0.35)"  # Currently focused

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
    COMMAND_BAR_HEIGHT = 42
    TRANSPORT_BAR_HEIGHT = 38
    STATUS_BAR_HEIGHT = 32
    CHAPTER_RAIL_WIDTH = 48
    POPOVER_WIDTH = 320

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
        """Apply command bar styling to a widget."""
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.SURFACE};
                border-bottom: 1px solid {Theme.BORDER};
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
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: 13px;
                    font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                }}
                QPushButton:hover {{
                    background-color: #4a5ce6;
                }}
                QPushButton:pressed {{
                    background-color: #3d4ed9;
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
                    padding: 8px 16px;
                    font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                    font-size: 13px;
                    font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                }}
                QPushButton:hover {{
                    background-color: {Theme.SURFACE_ALT};
                }}
                QPushButton:pressed {{
                    background-color: #e4e4e7;
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
                    background-color: #e4e4e7;
                }}
            """

        return ""

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
