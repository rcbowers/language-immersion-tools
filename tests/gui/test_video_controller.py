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
