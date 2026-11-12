"""VideoController playback behavior: subtitle tracking, seeking, periodic saves, load errors."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtMultimedia import QMediaPlayer

from immersion_app.core.video_service import VideoService
from immersion_app.gui.controllers import video_controller as vc
from immersion_app.media.subtitle_parser import SRTParser

SRT = """1
00:00:01,000 --> 00:00:02,000
Hola mundo

2
00:00:02,000 --> 00:00:04,000
Adios amigo

3
00:00:10,000 --> 00:00:12,000
Tercera linea
"""


class _Calls(list):
    def __call__(self, *args, **kwargs):
        self.append((args, kwargs))


class _Player:
    PlaybackState = QMediaPlayer.PlaybackState

    def __init__(self, state=QMediaPlayer.PlaybackState.StoppedState, position=0):
        self._state = state
        self._position = position
        self.positions = []
        self.played = 0
        self.paused = 0

    def playbackState(self):
        return self._state

    def position(self):
        return self._position

    def duration(self):
        return 60_000

    def setPosition(self, ms):
        self.positions.append(ms)

    def play(self):
        self.played += 1

    def pause(self):
        self.paused += 1


def _make(qtbot, tmp_path, player=None, with_subs=True, content_browser=None):
    service = VideoService()
    if with_subs:
        srt = tmp_path / "ep.srt"
        srt.write_text(SRT, encoding="utf-8")
        service.load_subtitles(str(srt))
    shown = []
    video_selection = SimpleNamespace(anchor=(1, 1), selected_indices=[1])
    window = SimpleNamespace(
        media_player=player or _Player(),
        _is_slider_dragging=False,
        transport_bar=SimpleNamespace(set_position=_Calls(), set_time=_Calls()),
        subtitle_offset_label=SimpleNamespace(setText=_Calls()),
        subtitle_label=SimpleNamespace(set_subtitle=lambda sub: shown.append(sub)),
        selection=SimpleNamespace(video=video_selection),
        current_source_location="",
        _fmt_ms=lambda ms: f"{ms // 1000}s",
        _fmt_offset=lambda ms: f"{ms:+d}ms",
        _update_source_summary=_Calls(),
        _close_popover=_Calls(),
        _persist_session=_Calls(),
        _iter_unique_clean_words=lambda words: iter(dict.fromkeys(w.lower() for w in words)),
        _set_status=_Calls(),
        current_srt_path="",
    )
    mining = SimpleNamespace(prefetch_translations=_Calls())
    controller = vc.VideoController(window, service, mining, content_browser_manager=content_browser)
    return controller, window, service, mining, shown


@pytest.fixture(autouse=True)
def _no_dialogs(monkeypatch):
    errors = _Calls()
    monkeypatch.setattr(vc.QMessageBox, "critical", errors)
    monkeypatch.setattr(vc.QMessageBox, "warning", errors)
    return errors


# --- subtitle highlighting ----------------------------------------------


def test_subtitle_shown_inside_cue_and_prefetched(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.on_position_changed(1500)
    assert controller.current_subtitle.text == "Hola mundo"
    assert shown[-1].text == "Hola mundo"
    assert mining.prefetch_translations == [((["hola", "mundo"],), {})]
    assert window._close_popover  # popover closes when the line changes


def test_cue_boundaries_current_behavior(qtbot, tmp_path):
    """Start is inclusive; end is inclusive too, but the next cue wins at a shared boundary."""
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.on_position_changed(999)
    assert controller.current_subtitle is None
    controller.on_position_changed(1000)
    assert controller.current_subtitle.index == 1
    controller.on_position_changed(2000)  # cue 1 ends and cue 2 starts at 2000
    assert controller.current_subtitle.index == 2
    controller.on_position_changed(4000)  # last ms of cue 2
    assert controller.current_subtitle.index == 2
    controller.on_position_changed(4001)
    assert controller.current_subtitle is None


def test_gap_clears_subtitle_and_selection(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.on_position_changed(1500)
    window.selection.video.anchor = (1, 0)
    window.selection.video.selected_indices = [0]
    controller.on_position_changed(6000)
    assert controller.current_subtitle is None
    assert shown[-1] is None
    assert window.selection.video.anchor is None and window.selection.video.selected_indices == []


def test_same_cue_does_not_reset_selection_or_refetch(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.on_position_changed(1100)
    window.selection.video.selected_indices = [0]
    controller.on_position_changed(1200)
    assert window.selection.video.selected_indices == [0]
    assert len(mining.prefetch_translations) == 1


def test_no_subtitles_loaded_is_safe(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path, with_subs=False)
    controller.on_position_changed(5000)
    assert controller.current_subtitle is None


def test_subtitle_offset_shifts_active_line(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.on_position_changed(1500)
    assert controller.current_subtitle.index == 1
    service.set_offset(500)  # subtitles appear 0.5 s later
    controller.on_position_changed(1200)
    assert controller.current_subtitle is None
    controller.on_position_changed(1500)
    assert controller.current_subtitle.index == 1
    service.set_offset(-500)  # subtitles appear 0.5 s earlier
    controller.on_position_changed(600)
    assert controller.current_subtitle.index == 1


def test_position_changed_updates_transport_and_offset_label(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    service.set_offset(500)
    controller.on_position_changed(3000)
    assert window.transport_bar.set_position == [((3000,), {})]
    assert window.transport_bar.set_time == [((3000, 60_000), {})]
    assert window.current_source_location == "3s"
    assert window.subtitle_offset_label.setText == [(("+500ms",), {})]


def test_slider_drag_does_not_fight_the_user(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    window._is_slider_dragging = True
    controller.on_position_changed(3000)
    assert window.transport_bar.set_position == []
    assert window.transport_bar.set_time  # the time label still updates


def test_usage_activity_recorded_at_most_once_a_minute_while_playing(qtbot, tmp_path):
    player = _Player(state=QMediaPlayer.PlaybackState.PlayingState)
    controller, window, service, mining, shown = _make(qtbot, tmp_path, player=player)
    tracker = SimpleNamespace(set_video_position_ms=_Calls(), record_activity=_Calls())
    window.usage_tracker = tracker
    controller.on_position_changed(1000)
    controller.on_position_changed(1500)
    assert len(tracker.record_activity) == 1
    assert len(tracker.set_video_position_ms) == 2


def test_no_activity_recorded_while_paused(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    tracker = SimpleNamespace(set_video_position_ms=_Calls(), record_activity=_Calls())
    window.usage_tracker = tracker
    controller.on_position_changed(1000)
    assert tracker.record_activity == []


# --- replay / toggle -----------------------------------------------------


def test_replay_seeks_to_current_cue_start(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.on_position_changed(3000)
    controller.replay_subtitle()
    assert window.media_player.positions == [2000]


def test_replay_with_no_subtitle_does_nothing(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.replay_subtitle()
    assert window.media_player.positions == []


def test_toggle_play_pause(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.toggle_play_pause()
    assert (window.media_player.played, window.media_player.paused) == (1, 0)
    window.media_player._state = QMediaPlayer.PlaybackState.PlayingState
    controller.toggle_play_pause()
    assert (window.media_player.played, window.media_player.paused) == (1, 1)


# --- loading subtitles ---------------------------------------------------


def test_load_subtitles_bad_file_shows_error_and_keeps_state(qtbot, tmp_path, _no_dialogs):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.load_subtitles(str(tmp_path / "does-not-exist.srt"))
    assert len(_no_dialogs) == 1 and "Failed to parse subtitles" in _no_dialogs[0][0][2]
    assert window.current_srt_path == ""
    assert service.subtitle_parser is not None  # previously loaded subtitles survive
    controller.on_position_changed(1500)
    assert controller.current_subtitle.index == 1  # player still usable


def test_load_subtitles_empty_srt_loads_without_crashing(qtbot, tmp_path, _no_dialogs):
    controller, window, service, mining, shown = _make(qtbot, tmp_path, with_subs=False)
    empty = tmp_path / "empty.srt"
    empty.write_text("", encoding="utf-8")
    controller.load_subtitles(str(empty))
    assert _no_dialogs == []
    assert window.current_srt_path == str(empty)
    assert window._persist_session
    controller.on_position_changed(1000)
    assert controller.current_subtitle is None


def test_load_subtitles_persists_session_and_reports_status(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path, with_subs=False)
    srt = tmp_path / "ok.srt"
    srt.write_text(SRT, encoding="utf-8")
    controller.load_subtitles(str(srt))
    assert window.current_srt_path == str(srt)
    assert len(window._persist_session) == 1
    assert window._set_status == [(("Loaded subtitles: ok.srt",), {})]


# --- loading videos ------------------------------------------------------


def test_load_missing_video_reports_error(qtbot, tmp_path, _no_dialogs):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.load_video(str(tmp_path / "nope.mp4"))
    assert "does not exist" in _no_dialogs[0][0][2]
    assert controller.current_video_path == ""


def test_load_tiny_video_is_rejected(qtbot, tmp_path, _no_dialogs):
    tiny = tmp_path / "tiny.mp4"
    tiny.write_bytes(b"x" * 10)
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    controller.load_video(str(tiny))
    assert "empty or corrupted" in _no_dialogs[0][0][2]
    assert controller.current_video_path == ""


# --- periodic save -------------------------------------------------------


def test_periodic_save_does_nothing_without_video(qtbot, tmp_path):
    browser = SimpleNamespace(update_last_position=_Calls())
    controller, window, service, mining, shown = _make(qtbot, tmp_path, content_browser=browser)
    controller._save_position_periodically()
    assert window._persist_session == [] and browser.update_last_position == []


def test_periodic_save_persists_session_and_position(qtbot, tmp_path):
    browser = SimpleNamespace(update_last_position=_Calls())
    player = _Player(position=42_000)
    controller, window, service, mining, shown = _make(qtbot, tmp_path, player=player, content_browser=browser)
    controller.current_video_path = "C:/v/ep.mp4"
    controller._save_position_periodically()
    assert len(window._persist_session) == 1
    assert browser.update_last_position == [(("C:/v/ep.mp4", {"video_position_ms": 42_000}), {})]


def test_position_save_timer_interval_is_30_seconds(qtbot, tmp_path):
    controller, *_ = _make(qtbot, tmp_path)
    assert controller._position_save_timer.interval() == 30_000


# --- subtitle clicks -----------------------------------------------------


def test_click_without_subtitle_is_ignored(qtbot, tmp_path):
    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    mining.request_translation = _Calls()
    controller.on_subtitle_click(0, 0)
    assert mining.request_translation == []


def test_click_single_word_selects_and_requests_translation(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    mining.request_translation = _Calls()
    window._clean_word = lambda w: w.lower().strip(".,")
    window.selection.set_video_selection = _Calls()
    window.subtitle_label.highlight_word_range = _Calls()
    controller.on_position_changed(1500)
    controller.on_subtitle_click(1, Qt.KeyboardModifier.NoModifier)
    assert mining.request_translation == [(("mundo",), {})]
    kwargs = window.selection.set_video_selection[0][1]
    assert kwargs["word"] == "mundo" and kwargs["sentence"] == "Hola mundo" and kwargs["selected_indices"] == [1]
    assert window.subtitle_label.highlight_word_range == [((1, 1), {})]


def test_shift_click_selects_phrase_using_raw_text(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    controller, window, service, mining, shown = _make(qtbot, tmp_path)
    mining.request_translation = _Calls()
    window._clean_word = lambda w: w.lower()
    window.selection.set_video_selection = _Calls()
    window.subtitle_label.highlight_word_range = _Calls()
    controller.on_position_changed(2500)  # "Adios amigo", cue index 2
    window.selection.video.anchor = (2, 0)
    controller.on_subtitle_click(1, Qt.KeyboardModifier.ShiftModifier)
    assert mining.request_translation == [(("Adios amigo",), {})]
    assert window.selection.set_video_selection[0][1]["selected_indices"] == [0, 1]
