from __future__ import annotations

import logging
import time as _time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QDialog, QMessageBox

from immersion_app.core.language_config import get_whisper_language_code
from immersion_app.core.mode import WorkspaceMode
from immersion_app.core.recent_files import add_recent_file
from immersion_app.core.user_data import save_user_data
from immersion_app.gui.widgets.subtitle_generator_dialog import SubtitleGeneratorDialog
from immersion_app.media.subtitle_matching import find_best_srt_for_video


class VideoController:
    def __init__(self, window, video_service, mining_controller, content_browser_manager=None):
        self.window = window
        self.video_service = video_service
        self.mining_controller = mining_controller
        self.content_browser_manager = content_browser_manager
        self.current_video_path = ""
        self.current_subtitle = None
        self._last_playback_activity_time: datetime | None = None
        self._last_position_changed_time: float | None = None  # perf_counter timestamp
        self._position_save_timer = QTimer()
        self._position_save_timer.setInterval(30_000)
        self._position_save_timer.timeout.connect(self._save_position_periodically)
        self._pending_restore_ms = 0
        self._restore_connected = False

    def load_video(self, path: str, restore_position_ms: int = 0):
        video_path = Path(path)
        if not video_path.exists():
            QMessageBox.critical(self.window, "File Not Found", f"Video file does not exist:\n{path}")
            return
        if video_path.stat().st_size < 1024:
            QMessageBox.warning(self.window, "Invalid File", f"Video file appears to be empty or corrupted:\n{video_path.name}")
            return
        self.current_video_path = path
        self.window.current_video_path = path
        self.window.current_source_name = video_path.name
        self.window.current_source_location = "00:00"
        if hasattr(self.window, "usage_tracker"):
            self.window.usage_tracker.on_video_loaded(path)
            self.window.usage_tracker.set_video_position_ms(restore_position_ms)
        if self._restore_connected:
            self.window.media_player.mediaStatusChanged.disconnect(self._on_restore_status_changed)
            self._restore_connected = False
        self._pending_restore_ms = restore_position_ms
        self.window._ensure_media_player()
        self.window.media_player.setSource(QUrl.fromLocalFile(path))
        if restore_position_ms > 0:
            self.window.media_player.mediaStatusChanged.connect(self._on_restore_status_changed)
            self._restore_connected = True
        auto_srt = find_best_srt_for_video(path)
        if auto_srt:
            self.load_subtitles(auto_srt)
        else:
            self.video_service.clear_subtitles()
            self.current_subtitle = None
            self.window.subtitle_label.set_subtitle(None)
        self.window._update_source_summary()
        self.window._persist_session()
        self.window.command_bar.set_title(video_path.name, "Video")
        self.window.command_bar.set_file_loaded(True)
        self.window._update_command_bar_stats()
        self.window.mode_manager.set_video_loaded(True)
        self.window.mode_manager.set_mode(WorkspaceMode.VIDEO, force=True)
        current_position = self.window.media_player.position() if self.window.media_player else 0
        add_recent_file(self.window.user_data, str(path), "video", {"video_position_ms": current_position})

        # Add to content browser
        if self.content_browser_manager:
            duration_ms = self.window.media_player.duration() if self.window.media_player else 0
            self.content_browser_manager.add_content(
                file_path=str(path),
                content_type="video",
                duration_ms=duration_ms if duration_ms > 0 else None,
                last_position={"video_position_ms": current_position}
            )

        save_user_data(self.window.user_data)
        self._position_save_timer.start()

    def load_subtitles(self, srt_path: str):
        try:
            parser = self.video_service.load_subtitles(srt_path)
        except Exception as exc:
            QMessageBox.critical(self.window, "Subtitle Error", f"Failed to parse subtitles:\n{exc}")
            return
        self.window.current_srt_path = srt_path
        self.window._persist_session()
        self.window._set_status(f"Loaded subtitles: {Path(srt_path).name}")
        if parser.subtitles:
            self.current_subtitle = None

    def generate_subtitles_interactive(self):
        if not self.current_video_path:
            QMessageBox.information(self.window, "No Video", "Open a video source first.")
            return
        dialog = SubtitleGeneratorDialog(self.window, default_language=get_whisper_language_code(self.window.learning_language))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        worker = self.window.create_subtitle_generation_worker(self.current_video_path, dialog.selected_model(), dialog.selected_language())
        dialog.status_label.setText("Starting generation...")
        dialog.progress_bar.setVisible(True)
        worker.signals.progress.connect(dialog.status_label.setText)
        worker.signals.finished.connect(lambda srt_path: self._on_generation_finished(dialog, srt_path))
        worker.signals.failed.connect(lambda message: QMessageBox.critical(self.window, "Subtitle Generation Error", message))
        self.window._subtitle_thread_pool.start(worker)

    def _on_generation_finished(self, dialog, srt_path: str):
        dialog.status_label.setText("Finished")
        self.load_subtitles(srt_path)
        self.window._set_status(f"Generated subtitles: {Path(srt_path).name}")

    def on_subtitle_click(self, token_index: int, modifiers):
        if not self.current_subtitle:
            return
        words = self.current_subtitle.words
        selected_indices, anchor = self.video_service.resolve_selection_range(
            token_index,
            bool(modifiers & Qt.KeyboardModifier.ShiftModifier),
            self.window.selection.video.anchor,
            self.current_subtitle.index,
            len(words),
        )
        cleaned_words = [self.window._clean_word(words[idx].word) for idx in selected_indices if self.window._clean_word(words[idx].word)]
        if not cleaned_words:
            return
        display_word = " ".join(cleaned_words)
        # For phrases, extract the span from the raw subtitle text so punctuation is preserved.
        # Single-word lookups use the cleaned form (no trailing comma/period).
        if len(selected_indices) == 1:
            translation_text = display_word
        else:
            first, last = selected_indices[0], selected_indices[-1]
            translation_text = self.current_subtitle.text[words[first].start:words[last].end].strip()
        self.window.selection.set_video_selection(
            word=display_word,
            sentence=self.current_subtitle.text,
            selected_indices=list(selected_indices),
            anchor=anchor,
        )
        self.window.current_source_location = self.window._fmt_ms(self.window.media_player.position())
        self.window.subtitle_label.highlight_word_range(selected_indices[0], selected_indices[-1])
        self.mining_controller.request_translation(translation_text)

    def on_position_changed(self, position: int):
        now = _time.perf_counter()
        is_playing = (
            self.window.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        if is_playing:
            if self._last_position_changed_time is not None:
                gap_ms = (now - self._last_position_changed_time) * 1000
                if gap_ms >= 1000:
                    logger.error("[VIDEO] positionChanged gap %.0fms — media player stalled", gap_ms)
                elif gap_ms >= 300:
                    logger.warning("[VIDEO] positionChanged gap %.0fms", gap_ms)
            self._last_position_changed_time = now
        else:
            self._last_position_changed_time = None

        if not self.window._is_slider_dragging:
            self.window.transport_bar.set_position(position)
        duration = self.window.media_player.duration()
        self.window.transport_bar.set_time(position, duration)
        self.window.current_source_location = self.window._fmt_ms(position)
        if hasattr(self.window, "usage_tracker"):
            self.window.usage_tracker.set_video_position_ms(position)
            if self.window.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                now = datetime.now()
                if (self._last_playback_activity_time is None or
                        (now - self._last_playback_activity_time).total_seconds() >= 60):
                    self.window.usage_tracker.record_activity()
                    self._last_playback_activity_time = now
        offset_text = self.window._fmt_offset(self.video_service.subtitle_offset_ms)
        self.window.subtitle_offset_label.setText(offset_text)
        self.refresh_subtitle_for_position(position)
        self.window._update_source_summary()

    def refresh_subtitle_for_position(self, position: int):
        subtitle = self.video_service.subtitle_at_position(position)
        if subtitle is None:
            self.current_subtitle = None
            self.window.selection.video.anchor = None
            self.window.selection.video.selected_indices = []
            self.window.subtitle_label.set_subtitle(None)
            self.window._close_popover()
            return
        if self.current_subtitle is None or subtitle.index != self.current_subtitle.index:
            self.current_subtitle = subtitle
            self.window.selection.video.anchor = None
            self.window.selection.video.selected_indices = []
            self.window.subtitle_label.set_subtitle(subtitle)
            words = list(self.window._iter_unique_clean_words(word.word for word in subtitle.words))
            self.mining_controller.prefetch_translations(words)
            self.window._close_popover()

    def replay_subtitle(self):
        if self.current_subtitle:
            self.window.media_player.setPosition(self.current_subtitle.start_ms)

    def toggle_play_pause(self):
        if self.window.media_player.playbackState() == self.window.media_player.PlaybackState.PlayingState:
            self.window.media_player.pause()
        else:
            self.window.media_player.play()

    def _on_restore_status_changed(self, status):
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self.window.media_player.setPosition(self._pending_restore_ms)
            self._pending_restore_ms = 0
            self.window.media_player.mediaStatusChanged.disconnect(self._on_restore_status_changed)
            self._restore_connected = False

    def _save_position_periodically(self):
        if not self.current_video_path:
            return
        t0 = _time.perf_counter()
        self.window._persist_session()
        persist_ms = (_time.perf_counter() - t0) * 1000
        update_ms = 0.0
        if self.content_browser_manager:
            t1 = _time.perf_counter()
            position = self.window.media_player.position() if self.window.media_player else 0
            self.content_browser_manager.update_last_position(
                self.current_video_path,
                {"video_position_ms": position}
            )
            update_ms = (_time.perf_counter() - t1) * 1000
        total_ms = persist_ms + update_ms
        if total_ms >= 20:
            logger.warning(
                "[PERIODIC-SAVE] persist=%.1fms update_pos=%.1fms total=%.1fms",
                persist_ms, update_ms, total_ms,
            )
        else:
            logger.debug(
                "[PERIODIC-SAVE] persist=%.1fms update_pos=%.1fms total=%.1fms",
                persist_ms, update_ms, total_ms,
            )
