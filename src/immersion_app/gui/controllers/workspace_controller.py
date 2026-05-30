from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from immersion_app.core.mode import WorkspaceMode
from immersion_app.core.queue_store import load_queue_entries
from immersion_app.core.recent_files import get_recent_files, remove_recent_file
from immersion_app.core.user_data import save_user_data


class WorkspaceController:
    def __init__(self, window, pdf_controller, video_controller):
        self.window = window
        self.pdf_controller = pdf_controller
        self.video_controller = video_controller

    def open_content_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self.window, "Open source", "", self.window.SUPPORTED_CONTENT_FILTER)
        if not path:
            return
        if Path(path).suffix.lower() == ".pdf":
            self.pdf_controller.load_pdf(path)
        else:
            self.video_controller.load_video(path)

    def close_current_file(self):
        if self.window.media_player:
            self.window.media_player.stop()
        if (
            self.window.mode_manager.current_mode == WorkspaceMode.VIDEO
            and getattr(self.window, "current_video_path", "")
            and hasattr(self.window, "usage_tracker")
        ):
            self.window.usage_tracker.on_video_closed()
        self.pdf_controller.pdf_service.close_document()
        self.video_controller.video_service.clear_subtitles()
        self.pdf_controller.current_pdf_path = ""
        self.video_controller.current_video_path = ""
        self.video_controller.current_subtitle = None
        self.window.current_source_name = ""
        self.window.current_pdf_path = ""
        self.window.current_video_path = ""
        self.window.current_srt_path = ""
        self.window._clear_selection_state()
        self.window.command_bar.set_title("No document loaded")
        self.window.command_bar.set_file_loaded(False)
        self.window.command_bar.set_page_info(0, 0)
        self.window._persist_session()
        self.window.mode_manager.set_pdf_loaded(False)
        self.window.mode_manager.set_video_loaded(False)
        self.window.mode_manager.set_mode(WorkspaceMode.WELCOME, force=True)

    def on_recent_file_selected(self, file_path: str, file_type: str):
        path = Path(file_path)
        if not path.exists():
            QMessageBox.critical(
                self.window,
                "File Not Found",
                f"The file no longer exists:\n{file_path}\n\nIt may have been moved or deleted.",
            )
            remove_recent_file(self.window.user_data, file_path)
            save_user_data(self.window.user_data)
            if hasattr(self.window, "welcome_recent_files_list"):
                self.window.welcome_recent_files_list.refresh()
            return
        recent_files = get_recent_files(self.window.user_data, validate_exists=False)
        file_entry = None
        normalized_path = os.path.normcase(os.path.abspath(file_path))
        for entry in recent_files:
            entry_path = os.path.normcase(os.path.abspath(entry.get("path", "")))
            if entry_path == normalized_path:
                file_entry = entry
                break
        if file_type == "pdf":
            self.pdf_controller.load_pdf(str(path), initial_page_index=file_entry.get("page_index", 0) if file_entry else 0)
        else:
            self.video_controller.load_video(str(path), restore_position_ms=file_entry.get("video_position_ms", 0) if file_entry else 0)

    def restore_last_session(self):
        session = self.window.user_data["last_session"]
        content_type = str(session.get("content_type") or "")
        pdf_path = str(session.get("pdf_path") or "")
        video_path = str(session.get("video_path") or "")

        def _try_video():
            if video_path and Path(video_path).exists():
                self.video_controller.video_service.set_offset(int(session.get("subtitle_offset_ms") or 0))
                self.video_controller.load_video(video_path, restore_position_ms=int(session.get("video_position_ms") or 0))
                srt_path = str(session.get("srt_path") or "")
                if srt_path and Path(srt_path).exists():
                    self.video_controller.load_subtitles(srt_path)
                return True
            return False

        def _try_pdf():
            if pdf_path and Path(pdf_path).exists():
                self.pdf_controller.load_pdf(pdf_path, initial_page_index=int(session.get("page_index") or 0))
                return True
            return False

        if content_type == "pdf":
            if _try_pdf() or _try_video():
                return
        else:
            if _try_video() or _try_pdf():
                return
