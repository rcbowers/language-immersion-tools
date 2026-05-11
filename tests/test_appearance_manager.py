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


class UserDataThemeModeTests(unittest.TestCase):
    def test_default_user_data_includes_theme_mode(self):
        payload = default_user_data()
        self.assertEqual(payload["preferences"]["theme_mode"], "light")
