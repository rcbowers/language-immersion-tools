"""Tests for WorkspaceController: routing recent files, restoring sessions, closing files."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from immersion_app.core.mode import WorkspaceMode
from immersion_app.core.recent_files import add_recent_file
from immersion_app.gui.controllers import workspace_controller as wc


class _Calls(list):
    def __call__(self, *args, **kwargs):
        self.append((args, kwargs))


def _make(user_data=None):
    pdf = SimpleNamespace(
        load_pdf=_Calls(),
        pdf_service=SimpleNamespace(close_document=_Calls()),
        current_pdf_path="x.pdf",
    )
    video = SimpleNamespace(
        load_video=_Calls(),
        load_subtitles=_Calls(),
        video_service=SimpleNamespace(clear_subtitles=_Calls(), set_offset=_Calls()),
        current_video_path="x.mp4",
        current_subtitle=object(),
    )
    modes = SimpleNamespace(
        current_mode=WorkspaceMode.PDF,
        set_pdf_loaded=_Calls(),
        set_video_loaded=_Calls(),
        set_mode=_Calls(),
    )
    window = SimpleNamespace(
        SUPPORTED_CONTENT_FILTER="All (*)",
        user_data=user_data if user_data is not None else {"recent_files": [], "last_session": {}},
        media_player=SimpleNamespace(stop=_Calls()),
        mode_manager=modes,
        usage_tracker=SimpleNamespace(on_video_closed=_Calls()),
        command_bar=SimpleNamespace(set_title=_Calls(), set_file_loaded=_Calls(), set_page_info=_Calls()),
        welcome_recent_files_list=SimpleNamespace(refresh=_Calls()),
        _clear_selection_state=_Calls(),
        _persist_session=_Calls(),
        current_source_name="Book",
        current_pdf_path="x.pdf",
        current_video_path="x.mp4",
        current_srt_path="x.srt",
    )
    return wc.WorkspaceController(window, pdf, video), window, pdf, video


@pytest.fixture(autouse=True)
def _no_disk_or_dialogs(monkeypatch):
    saved = _Calls()
    errors = _Calls()
    monkeypatch.setattr(wc, "save_user_data", saved)
    monkeypatch.setattr(wc.QMessageBox, "critical", errors)
    return SimpleNamespace(saved=saved, errors=errors)


# --- open dialog ---------------------------------------------------------


def test_open_dialog_routes_by_extension(monkeypatch):
    controller, window, pdf, video = _make()
    monkeypatch.setattr(wc.QFileDialog, "getOpenFileName", lambda *a: ("C:/books/Libro.PDF", ""))
    controller.open_content_dialog()
    assert pdf.load_pdf == [(("C:/books/Libro.PDF",), {})]
    monkeypatch.setattr(wc.QFileDialog, "getOpenFileName", lambda *a: ("C:/v/ep1.mkv", ""))
    controller.open_content_dialog()
    assert video.load_video == [(("C:/v/ep1.mkv",), {})]


def test_open_dialog_cancel_does_nothing(monkeypatch):
    controller, window, pdf, video = _make()
    monkeypatch.setattr(wc.QFileDialog, "getOpenFileName", lambda *a: ("", ""))
    controller.open_content_dialog()
    assert not pdf.load_pdf and not video.load_video


# --- recent files --------------------------------------------------------


def test_recent_pdf_passes_saved_page(tmp_path):
    book = tmp_path / "book.pdf"
    book.write_bytes(b"%PDF")
    data = {"recent_files": [], "last_session": {}}
    add_recent_file(data, str(book), "pdf", {"page_index": 41})
    controller, window, pdf, video = _make(data)
    controller.on_recent_file_selected(str(book), "pdf")
    assert pdf.load_pdf == [((str(book),), {"initial_page_index": 41})]
    assert not video.load_video


def test_recent_video_passes_saved_position(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x" * 10)
    data = {"recent_files": [], "last_session": {}}
    add_recent_file(data, str(clip), "video", {"video_position_ms": 90_000})
    controller, window, pdf, video = _make(data)
    controller.on_recent_file_selected(str(clip), "video")
    assert video.load_video == [((str(clip),), {"restore_position_ms": 90_000})]


def test_recent_file_not_in_list_starts_at_zero(tmp_path):
    book = tmp_path / "other.pdf"
    book.write_bytes(b"%PDF")
    controller, window, pdf, video = _make()
    controller.on_recent_file_selected(str(book), "pdf")
    assert pdf.load_pdf == [((str(book),), {"initial_page_index": 0})]


def test_missing_recent_file_is_removed_and_user_told(tmp_path, _no_disk_or_dialogs):
    gone = tmp_path / "gone.pdf"
    data = {"recent_files": [], "last_session": {}}
    add_recent_file(data, str(gone), "pdf", {})
    controller, window, pdf, video = _make(data)
    controller.on_recent_file_selected(str(gone), "pdf")
    assert data["recent_files"] == []
    assert len(_no_disk_or_dialogs.errors) == 1  # told, not crashed
    assert "no longer exists" in _no_disk_or_dialogs.errors[0][0][2]
    assert len(_no_disk_or_dialogs.saved) == 1
    assert len(window.welcome_recent_files_list.refresh) == 1
    assert not pdf.load_pdf and not video.load_video


# --- restore last session ------------------------------------------------


def _session(tmp_path, **overrides):
    files = {}
    for name in ("book.pdf", "clip.mp4", "clip.srt"):
        path = tmp_path / name
        path.write_bytes(b"x")
        files[name] = str(path)
    session = {
        "content_type": "video",
        "pdf_path": files["book.pdf"],
        "video_path": files["clip.mp4"],
        "srt_path": files["clip.srt"],
        "page_index": 7,
        "video_position_ms": 12_000,
        "subtitle_offset_ms": 500,
    }
    session.update(overrides)
    return session, files


def test_restore_video_session_with_subtitles_and_offset(tmp_path):
    session, files = _session(tmp_path)
    controller, window, pdf, video = _make({"recent_files": [], "last_session": session})
    controller.restore_last_session()
    assert video.video_service.set_offset == [((500,), {})]
    assert video.load_video == [((files["clip.mp4"],), {"restore_position_ms": 12_000})]
    assert video.load_subtitles == [((files["clip.srt"],), {})]
    assert not pdf.load_pdf


def test_restore_pdf_session(tmp_path):
    session, files = _session(tmp_path, content_type="pdf")
    controller, window, pdf, video = _make({"recent_files": [], "last_session": session})
    controller.restore_last_session()
    assert pdf.load_pdf == [((files["book.pdf"],), {"initial_page_index": 7})]
    assert not video.load_video


def test_restore_falls_through_to_pdf_when_video_is_gone(tmp_path):
    session, files = _session(tmp_path, video_path=str(tmp_path / "missing.mp4"))
    controller, window, pdf, video = _make({"recent_files": [], "last_session": session})
    controller.restore_last_session()
    assert not video.load_video
    assert pdf.load_pdf == [((files["book.pdf"],), {"initial_page_index": 7})]


def test_restore_falls_through_to_video_when_pdf_is_gone(tmp_path):
    session, files = _session(tmp_path, content_type="pdf", pdf_path=str(tmp_path / "missing.pdf"))
    controller, window, pdf, video = _make({"recent_files": [], "last_session": session})
    controller.restore_last_session()
    assert not pdf.load_pdf
    assert video.load_video


def test_restore_skips_missing_subtitle_file(tmp_path):
    session, files = _session(tmp_path, srt_path=str(tmp_path / "gone.srt"))
    controller, window, pdf, video = _make({"recent_files": [], "last_session": session})
    controller.restore_last_session()
    assert video.load_video and not video.load_subtitles


def test_restore_with_nothing_saved_loads_nothing():
    controller, window, pdf, video = _make({"recent_files": [], "last_session": {}})
    controller.restore_last_session()
    assert not pdf.load_pdf and not video.load_video and not window.mode_manager.set_mode


def test_restore_with_none_values_does_not_crash():
    session = {"content_type": None, "pdf_path": None, "video_path": None, "page_index": None}
    controller, window, pdf, video = _make({"recent_files": [], "last_session": session})
    controller.restore_last_session()
    assert not pdf.load_pdf and not video.load_video


# --- close ---------------------------------------------------------------


def test_close_current_video_resets_everything():
    controller, window, pdf, video = _make()
    window.mode_manager.current_mode = WorkspaceMode.VIDEO
    controller.close_current_file()

    assert len(window.media_player.stop) == 1
    assert len(window.usage_tracker.on_video_closed) == 1
    assert len(pdf.pdf_service.close_document) == 1
    assert len(video.video_service.clear_subtitles) == 1
    assert pdf.current_pdf_path == "" and video.current_video_path == "" and video.current_subtitle is None
    assert (window.current_source_name, window.current_pdf_path, window.current_video_path, window.current_srt_path) == ("", "", "", "")
    assert len(window._clear_selection_state) == 1
    assert window.command_bar.set_title == [(("No document loaded",), {})]
    assert window.command_bar.set_file_loaded == [((False,), {})]
    assert window.command_bar.set_page_info == [((0, 0), {})]
    assert window.mode_manager.set_pdf_loaded == [((False,), {})]
    assert window.mode_manager.set_video_loaded == [((False,), {})]
    assert window.mode_manager.set_mode == [((WorkspaceMode.WELCOME,), {"force": True})]


def test_close_persists_session_before_mode_reset():
    controller, window, pdf, video = _make()
    order = []
    window._persist_session = lambda: order.append("persist")
    window.mode_manager.set_mode = lambda *a, **k: order.append("mode")
    controller.close_current_file()
    assert order == ["persist", "mode"]


def test_close_pdf_does_not_report_video_closed():
    controller, window, pdf, video = _make()
    window.mode_manager.current_mode = WorkspaceMode.PDF
    controller.close_current_file()
    assert window.usage_tracker.on_video_closed == []


def test_close_without_media_player_is_safe():
    controller, window, pdf, video = _make()
    window.media_player = None
    controller.close_current_file()
    assert window.mode_manager.set_mode
