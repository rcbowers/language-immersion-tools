import unittest

from PySide6.QtCore import QObject

from immersion_app.core.appearance_manager import AppearanceManager, AppearanceMode
from immersion_app.core.user_data import default_user_data, load_user_data


class _SignalCapture(QObject):
    def __init__(self):
        super().__init__()
        self.modes = []

    def on_changed(self, mode: str):
        self.modes.append(mode)


class AppearanceManagerTests(unittest.TestCase):
    def test_defaults_to_light_mode(self):
        manager = AppearanceManager()
        self.assertEqual(manager.current_mode, AppearanceMode.LIGHT)
        self.assertEqual(manager.mode_string(), "light")

    def test_emits_when_mode_changes(self):
        manager = AppearanceManager("light")
        capture = _SignalCapture()
        manager.appearance_changed.connect(capture.on_changed)

        changed = manager.set_mode("dark")

        self.assertTrue(changed)
        self.assertEqual(manager.current_mode, AppearanceMode.DARK)
        self.assertEqual(capture.modes, ["dark"])

    def test_no_signal_when_setting_same_mode(self):
        manager = AppearanceManager("dark")
        capture = _SignalCapture()
        manager.appearance_changed.connect(capture.on_changed)

        changed = manager.set_mode("dark")

        self.assertFalse(changed)
        self.assertEqual(capture.modes, [])

    def test_accepts_new_themes_and_reports_dark(self):
        manager = AppearanceManager("nord")
        self.assertEqual(manager.current_mode, AppearanceMode.NORD)
        self.assertTrue(manager.is_dark)
        manager.set_mode("sepia")
        self.assertFalse(manager.is_dark)

    def test_unknown_theme_falls_back_to_light(self):
        self.assertEqual(AppearanceManager("bogus").current_mode, AppearanceMode.LIGHT)

    def test_toggle_switches_between_light_and_dark_families(self):
        manager = AppearanceManager("midnight")
        manager.toggle_mode()
        self.assertEqual(manager.current_mode, AppearanceMode.LIGHT)
        manager = AppearanceManager("sepia")
        manager.toggle_mode()
        self.assertEqual(manager.current_mode, AppearanceMode.DARK)

    def test_available_themes_lists_every_mode(self):
        from immersion_app.core.appearance_manager import available_themes

        self.assertEqual([theme_id for theme_id, _ in available_themes()], [m.value for m in AppearanceMode])


class UserDataThemeModeTests(unittest.TestCase):
    def test_new_theme_persists_and_unknown_resets(self):
        import json

        from immersion_app.core import user_data

        state_path = user_data.USER_STATE_PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        original = state_path.read_text(encoding="utf-8") if state_path.exists() else None
        try:
            for stored, expected in (("solarized_dark", "solarized_dark"), ("bogus", "light"), ("dark", "dark")):
                state_path.write_text(json.dumps({"preferences": {"theme_mode": stored}}), encoding="utf-8")
                self.assertEqual(user_data.load_user_data()["preferences"]["theme_mode"], expected)
        finally:
            if original is None:
                state_path.unlink(missing_ok=True)
            else:
                state_path.write_text(original, encoding="utf-8")
