"""WorkspaceController routing of EPUB files and restoration of chapter locations."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from immersion_app.gui.controllers.workspace_controller import WorkspaceController


def _controller(user_data=None):
    window = SimpleNamespace(
        SUPPORTED_CONTENT_FILTER="x",
        user_data=user_data if user_data is not None else {"recent_files": [], "last_session": {}},
    )
    pdf, video = MagicMock(), MagicMock()
    return WorkspaceController(window, pdf, video), pdf, video


def test_open_dialog_routes_epub_to_document_controller(tmp_path):
    controller, pdf, video = _controller()
    path = str(tmp_path / "libro.EPUB")

    with patch("immersion_app.gui.controllers.workspace_controller.QFileDialog.getOpenFileName", return_value=(path, "")):
        controller.open_content_dialog()

    pdf.load_pdf.assert_called_once_with(path)
    video.load_video.assert_not_called()


def test_open_dialog_still_routes_video_to_video_controller(tmp_path):
    controller, pdf, video = _controller()
    path = str(tmp_path / "clip.mp4")

    with patch("immersion_app.gui.controllers.workspace_controller.QFileDialog.getOpenFileName", return_value=(path, "")):
        controller.open_content_dialog()

    video.load_video.assert_called_once_with(path)
    pdf.load_pdf.assert_not_called()


def test_recent_epub_restores_via_chapter_location(tmp_path):
    book = tmp_path / "libro.epub"
    book.write_bytes(b"x")
    user_data = {
        "recent_files": [
            {"path": str(book), "type": "epub", "page_index": 5, "chapter": 1, "chapter_page": 2},
        ],
        "last_session": {},
    }
    controller, pdf, _video = _controller(user_data)

    controller.on_recent_file_selected(str(book), "epub")

    pdf.load_pdf.assert_called_once_with(str(book), initial_page_index=5, initial_location=(1, 2))


def test_recent_pdf_has_no_location(tmp_path):
    book = tmp_path / "libro.pdf"
    book.write_bytes(b"x")
    user_data = {"recent_files": [{"path": str(book), "type": "pdf", "page_index": 4}], "last_session": {}}
    controller, pdf, _video = _controller(user_data)

    controller.on_recent_file_selected(str(book), "pdf")

    pdf.load_pdf.assert_called_once_with(str(book), initial_page_index=4, initial_location=None)


def test_restore_last_session_passes_chapter_location(tmp_path):
    book = tmp_path / "libro.epub"
    book.write_bytes(b"x")
    session = {
        "content_type": "pdf",
        "pdf_path": str(book),
        "page_index": 7,
        "chapter": 2,
        "chapter_page": 1,
        "video_path": "",
    }
    controller, pdf, _video = _controller({"recent_files": [], "last_session": session})

    controller.restore_last_session()

    pdf.load_pdf.assert_called_once_with(str(book), initial_page_index=7, initial_location=(2, 1))
