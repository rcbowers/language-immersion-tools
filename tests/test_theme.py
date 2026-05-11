"""Unit tests for theme stylesheet helpers."""

import unittest

from immersion_app.gui.theme import Theme


class ThemeTests(unittest.TestCase):
    """Test cases for Theme stylesheet helpers."""

    def test_get_scrollbar_style_vertical_default(self):
        """Vertical scrollbar style is returned by default."""
        style = Theme.get_scrollbar_style()

        self.assertIn("QScrollBar:vertical", style)
        self.assertIn(f"background-color: {Theme.TEXT_MUTED};", style)
        self.assertIn(f"background-color: {Theme.TEXT};", style)
        self.assertNotIn("QScrollBar:horizontal", style)

    def test_get_scrollbar_style_horizontal(self):
        """Horizontal scrollbar style is returned when requested."""
        style = Theme.get_scrollbar_style("horizontal")

        self.assertIn("QScrollBar:horizontal", style)
        self.assertIn("min-width: 20px;", style)
        self.assertNotIn("QScrollBar:vertical", style)

    def test_get_scrollbar_style_both(self):
        """Combined scrollbar style includes both orientations."""
        style = Theme.get_scrollbar_style("both")

        self.assertIn("QScrollBar:vertical", style)
        self.assertIn("QScrollBar:horizontal", style)

    def test_get_scrollbar_style_invalid_orientation(self):
        """Invalid orientations raise a helpful error."""
        with self.assertRaises(ValueError):
            Theme.get_scrollbar_style("diagonal")

    def test_apply_mode_switches_runtime_palette(self):
        Theme.apply_mode("dark")
        try:
            self.assertTrue(Theme.is_dark())
            self.assertEqual(Theme.current_mode(), "dark")
            self.assertEqual(Theme.BG, "#111318")
            self.assertIn(Theme.SURFACE, Theme.get_menu_style())
        finally:
            Theme.apply_mode("light")


if __name__ == "__main__":
    unittest.main()
