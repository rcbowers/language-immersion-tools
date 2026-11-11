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

    def test_every_theme_has_a_palette_with_identical_tokens(self):
        from immersion_app.core.appearance_manager import AppearanceMode

        self.assertEqual(set(Theme._PALETTES), {mode.value for mode in AppearanceMode})
        reference = set(Theme._PALETTES["light"])
        for theme_id, palette in Theme._PALETTES.items():
            self.assertEqual(set(palette), reference, theme_id)
            self.assertTrue(all(palette.values()), theme_id)

    def test_is_dark_follows_theme_registry(self):
        expected = {
            "light": False, "sepia": False, "forest": False,
            "dark": True, "nord": True, "solarized_dark": True, "midnight": True,
        }
        try:
            for theme_id, dark in expected.items():
                Theme.apply_mode(theme_id)
                self.assertEqual(Theme.current_mode(), theme_id)
                self.assertEqual(Theme.is_dark(), dark, theme_id)
        finally:
            Theme.apply_mode("light")

    def test_unknown_theme_falls_back_to_light(self):
        try:
            Theme.apply_mode("neon-pink")
            self.assertEqual(Theme.current_mode(), "light")
            self.assertFalse(Theme.is_dark())
        finally:
            Theme.apply_mode("light")


if __name__ == "__main__":
    unittest.main()
