import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from immersion_app.gui.controllers.video_controller import VideoController


class MockMediaPlayer(QObject):
    mediaStatusChanged = Signal(QMediaPlayer.MediaStatus)

    def __init__(self):
        super().__init__()
        self.set_position_calls = []

    def setPosition(self, ms):
        self.set_position_calls.append(ms)

    def position(self):
        return 0

    def duration(self):
        return 0

    def setSource(self, url):
        pass


def _make_window(media_player):
    return SimpleNamespace(
        media_player=media_player,
        current_video_path="",
        current_source_name="",
        current_source_location="",
        _update_source_summary=lambda: None,
        _persist_session=lambda: None,
        _update_command_bar_stats=lambda: None,
        command_bar=SimpleNamespace(set_title=lambda *a: None, set_file_loaded=lambda *a: None),
        mode_manager=SimpleNamespace(set_video_loaded=lambda *a: None, set_mode=lambda *a, **kw: None),
        user_data={"recent_files": []},
        subtitle_label=SimpleNamespace(set_subtitle=lambda *a: None),
        transport_bar=SimpleNamespace(set_position=lambda *a: None, set_time=lambda *a: None),
    )


class VideoControllerRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_controller(self):
        player = MockMediaPlayer()
        window = _make_window(player)
        video_service = SimpleNamespace(
            subtitle_parser=None,
            subtitle_offset_ms=0,
            clear_subtitles=lambda: None,
        )
        mining_controller = SimpleNamespace(prefetch_translations=lambda *a: None)
        ctrl = VideoController(window, video_service, mining_controller)
        return ctrl, player

    def test_restore_seeks_on_loaded_media(self):
        ctrl, player = self._make_controller()
        ctrl._pending_restore_ms = 5000
        ctrl._restore_connected = True
        player.mediaStatusChanged.connect(ctrl._on_restore_status_changed)

        player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.LoadedMedia)

        self.assertEqual(player.set_position_calls, [5000])
        self.assertEqual(ctrl._pending_restore_ms, 0)
        self.assertFalse(ctrl._restore_connected)

    def test_restore_seeks_on_buffered_media(self):
        ctrl, player = self._make_controller()
        ctrl._pending_restore_ms = 3000
        ctrl._restore_connected = True
        player.mediaStatusChanged.connect(ctrl._on_restore_status_changed)

        player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.BufferedMedia)

        self.assertEqual(player.set_position_calls, [3000])
        self.assertEqual(ctrl._pending_restore_ms, 0)
        self.assertFalse(ctrl._restore_connected)

    def test_restore_ignored_for_loading_status(self):
        ctrl, player = self._make_controller()
        ctrl._pending_restore_ms = 5000
        ctrl._restore_connected = True
        player.mediaStatusChanged.connect(ctrl._on_restore_status_changed)

        player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.LoadingMedia)

        self.assertEqual(player.set_position_calls, [])
        self.assertEqual(ctrl._pending_restore_ms, 5000)
        self.assertTrue(ctrl._restore_connected)

    def test_restore_disconnects_after_seek(self):
        ctrl, player = self._make_controller()
        ctrl._pending_restore_ms = 5000
        ctrl._restore_connected = True
        player.mediaStatusChanged.connect(ctrl._on_restore_status_changed)

        player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.LoadedMedia)
        self.assertEqual(player.set_position_calls, [5000])

        # Second emit must not call setPosition again (handler was disconnected)
        player.mediaStatusChanged.emit(QMediaPlayer.MediaStatus.LoadedMedia)
        self.assertEqual(player.set_position_calls, [5000])

    def test_initial_state_no_restore_pending(self):
        ctrl, _ = self._make_controller()
        self.assertEqual(ctrl._pending_restore_ms, 0)
        self.assertFalse(ctrl._restore_connected)


if __name__ == "__main__":
    unittest.main()


class VideoControllerSubtitleClickTests(unittest.TestCase):
    """Clicking subtitle words selects them and requests a translation (ported from the legacy window path)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make(self, text):


        from immersion_app.core.selection_state import SelectionState
        from immersion_app.core.video_service import VideoService
        from immersion_app.media.subtitle_parser import SRTParser

        subtitle = SRTParser.from_text(f"1\n00:00:00,000 --> 00:00:02,000\n{text}").subtitles[0]
        requested, highlighted = [], []
        window = _make_window(MockMediaPlayer())
        window.selection = SelectionState()
        window._clean_word = lambda value: value.strip(".,¿?¡!").strip()
        window._fmt_ms = lambda ms: "00:00"
        window.subtitle_label = SimpleNamespace(highlight_word_range=lambda a, b: highlighted.append((a, b)))
        mining = SimpleNamespace(request_translation=requested.append, prefetch_translations=lambda *a: None)
        ctrl = VideoController(window, VideoService(), mining)
        ctrl.current_subtitle = subtitle
        return ctrl, window, subtitle, requested, highlighted

    def test_click_selects_word_and_requests_translation(self):
        from PySide6.QtCore import Qt

        ctrl, window, subtitle, requested, highlighted = self._make("hola, mundo cruel.")
        ctrl.on_subtitle_click(0, Qt.KeyboardModifier.NoModifier)

        self.assertEqual(window.selection.word, "hola")
        self.assertEqual(window.selection.sentence, subtitle.text)
        self.assertEqual(requested, ["hola"])
        self.assertEqual(highlighted, [(0, 0)])

    def test_shift_click_extends_to_phrase_with_punctuation(self):
        from PySide6.QtCore import Qt

        ctrl, window, _subtitle, requested, highlighted = self._make("hola, mundo cruel.")
        ctrl.on_subtitle_click(0, Qt.KeyboardModifier.NoModifier)
        ctrl.on_subtitle_click(2, Qt.KeyboardModifier.ShiftModifier)

        self.assertEqual(window.selection.word, "hola mundo cruel")
        self.assertEqual(requested[-1], "hola, mundo cruel")  # inner punctuation kept for the translator
        self.assertEqual(highlighted[-1], (0, 2))
