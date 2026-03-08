#!/usr/bin/env python3
"""Video sentence miner window."""

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from base_miner_window import AbstractSentenceMinerWindow
from subtitle_generator import generate_srt_from_video
from subtitle_matching import find_best_srt_for_video
from subtitle_parser import SRTParser
from subtitle_widget import ClickableSubtitleLabel


class SubtitleGenerationSignals(QObject):
    progress = Signal(str)
    finished = Signal(str)
    failed = Signal(str)


class SubtitleGeneratorWorker(QRunnable):
    def __init__(self, video_path, model_size, language):
        super().__init__()
        self.video_path = video_path
        self.model_size = model_size
        self.language = language
        self.signals = SubtitleGenerationSignals()

    def run(self):
        try:
            path = generate_srt_from_video(
                self.video_path,
                output_path=str(Path(self.video_path).with_suffix(".srt")),
                model_size=self.model_size,
                language=self.language,
                progress_callback=lambda msg: self.signals.progress.emit(msg),
            )
            self.signals.finished.emit(path)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class SubtitleGeneratorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Subtitles")
        self.resize(420, 220)

        layout = QVBoxLayout(self)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium"])
        self.model_combo.setCurrentText("base")
        model_row.addWidget(self.model_combo)
        layout.addLayout(model_row)

        language_row = QHBoxLayout()
        language_row.addWidget(QLabel("Language:"))
        self.language_input = QLineEdit("es")
        language_row.addWidget(self.language_input)
        layout.addLayout(language_row)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("Generate")
        self.cancel_button = QPushButton("Cancel")
        self.start_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)

    def selected_model(self):
        return self.model_combo.currentText()

    def selected_language(self):
        return self.language_input.text().strip() or "es"


class VideoSentenceMinerWindow(AbstractSentenceMinerWindow):
    SUPPORTED_VIDEO_FILTER = "Video Files (*.mp4 *.mkv *.avi *.mov *.webm)"
    SUPPORTED_CONTENT_FILTER = "Content Files (*.pdf *.mp4 *.mkv *.avi *.mov *.webm)"

    def __init__(self):
        self.media_player = None
        self.audio_output = None
        self.video_widget = None

        self.subtitle_label = None
        self.subtitle_parser = None
        self.current_subtitle = None

        self.current_video_path = ""
        self.current_srt_path = ""

        self.play_pause_button = None
        self.play_pause_toolbar_action = None
        self.position_slider = None
        self.subtitle_offset_label = None
        self.time_label = None
        self.speed_action_group = None
        self.speed_menu_actions = {}
        self._is_slider_dragging = False
        self.subtitle_offset_ms = 0
        self._session_timer = QTimer()
        self._session_timer.setInterval(5000)

        self._subtitle_thread_pool = QThreadPool.globalInstance()

        super().__init__("Spanish Video Sentence Miner")
        self._add_offset_status_to_right_panel()

        self._session_timer.timeout.connect(self._persist_last_session)
        self._session_timer.start()

    def _add_offset_status_to_right_panel(self):
        if not self.right_panel:
            return
        layout = self.right_panel.layout()
        if not layout:
            return

        self.subtitle_offset_label = QLabel("Offset: +0.00s")

        insert_index = layout.count()
        if self.mode_indicator_label:
            mode_idx = layout.indexOf(self.mode_indicator_label)
            if mode_idx >= 0:
                insert_index = mode_idx + 1
        layout.insertWidget(insert_index, self.subtitle_offset_label)

    def _build_mode_toolbar(self):
        toolbar = QToolBar("Video Tools")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        content_menu = QMenu("Content", self)
        self._add_menu_action(content_menu, "Open content", self._open_content_dialog, shortcuts="Ctrl+O")

        speed_menu = content_menu.addMenu("Video speed")
        self.speed_action_group = QActionGroup(self)
        self.speed_action_group.setExclusive(True)
        self.speed_menu_actions = {}
        for speed in (0.5, 0.75, 1.0, 1.25, 1.5):
            speed_text = f"{speed:.2f}x".replace(".00", ".0")
            action = QAction(speed_text, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, value=speed: self._set_video_speed(value))
            self.speed_action_group.addAction(action)
            speed_menu.addAction(action)
            self.speed_menu_actions[speed] = action
        self._add_toolbar_menu_button(toolbar, "Content", content_menu)

        subtitles_menu = QMenu("Subtitles", self)
        self._add_menu_action(subtitles_menu, "Load subtitles", self._open_subtitle_dialog, shortcuts="Ctrl+L")
        self._add_menu_action(subtitles_menu, "Generate subtitles", self._generate_subtitles_interactive)
        subtitles_menu.addSeparator()
        self._add_menu_action(subtitles_menu, "Sub -0.25s", lambda: self._adjust_subtitle_offset(-250))
        self._add_menu_action(subtitles_menu, "Sub +0.25s", lambda: self._adjust_subtitle_offset(250))
        self._add_toolbar_menu_button(toolbar, "Subtitles", subtitles_menu)

        playback_menu = QMenu("Playback", self)
        self.play_pause_toolbar_action = QAction("▶️", self)
        self.play_pause_toolbar_action.setToolTip("Play/Pause")
        self.play_pause_toolbar_action.triggered.connect(self._toggle_play_pause)
        playback_menu.addAction(self.play_pause_toolbar_action)
        self._add_menu_action(playback_menu, "Seek -5s", lambda: self._seek_relative(-5000))
        self._add_menu_action(playback_menu, "Seek +5s", lambda: self._seek_relative(5000))
        self._add_toolbar_menu_button(toolbar, "Playback", playback_menu)

        toolbar.addSeparator()
        self._build_common_toolbar_menus(toolbar)

        play_action = QAction("Play/Pause", self)
        play_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        play_action.triggered.connect(self._toggle_play_pause)
        self.addAction(play_action)

        back_action = QAction("Back 5s", self)
        back_action.setShortcut(QKeySequence(Qt.Key.Key_Left))
        back_action.triggered.connect(lambda: self._seek_relative(-5000))
        self.addAction(back_action)

        fwd_action = QAction("Forward 5s", self)
        fwd_action.setShortcut(QKeySequence(Qt.Key.Key_Right))
        fwd_action.triggered.connect(lambda: self._seek_relative(5000))
        self.addAction(fwd_action)

        subtitle_left_action = QAction("Subtitle offset left", self)
        subtitle_left_action.setShortcut(QKeySequence(Qt.Key.Key_Comma))
        subtitle_left_action.triggered.connect(lambda: self._adjust_subtitle_offset(-250))
        self.addAction(subtitle_left_action)

        subtitle_right_action = QAction("Subtitle offset right", self)
        subtitle_right_action.setShortcut(QKeySequence(Qt.Key.Key_Period))
        subtitle_right_action.triggered.connect(lambda: self._adjust_subtitle_offset(250))
        self.addAction(subtitle_right_action)

    def _build_viewer_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(480)
        layout.addWidget(self.video_widget, stretch=1)

        timeline_widget = QWidget(panel)
        timeline_widget.setFixedHeight(22)
        timeline_layout = QHBoxLayout(timeline_widget)
        timeline_layout.setContentsMargins(8, 4, 8, 4)
        self.play_pause_button = QPushButton('▶️')
        self.play_pause_button.setToolTip("Play/Pause")
        self.play_pause_button.clicked.connect(self._toggle_play_pause)
        timeline_layout.addWidget(self.play_pause_button)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        timeline_layout.addWidget(self.position_slider, stretch=1)

        self.time_label = QLabel("00:00 / 00:00")
        timeline_layout.addWidget(self.time_label)
        layout.addWidget(timeline_widget)

        self.subtitle_label = ClickableSubtitleLabel(panel)
        self.subtitle_label.setFixedHeight(96)
        self.subtitle_label.set_subtitle_text("")
        self.subtitle_label.show()
        self.subtitle_label.clicked.connect(self._on_subtitle_click)
        layout.addWidget(self.subtitle_label)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)

        self._set_transport_enabled_state()
        return panel

    def _open_video_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Video", "", self.SUPPORTED_VIDEO_FILTER)
        if not path:
            return
        self._load_video(path)

    def _open_content_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open content", "", self.SUPPORTED_CONTENT_FILTER)
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext == ".pdf":
            self._switch_to_pdf_mode(path)
            return
        self._load_video(path)

    def _switch_to_pdf_mode(self, pdf_path):
        from pdf_miner_window import PdfSentenceMinerWindow

        window = PdfSentenceMinerWindow()
        window.show()
        window._load_pdf(pdf_path)
        window.user_data["mode"] = "pdf"
        window._save_user_data()
        self.close()

    def _open_subtitle_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Subtitles", "", "SRT Files (*.srt)")
        if not path:
            return
        self._load_subtitles(path)

    def _load_video(self, path, restore_position_ms=0):
        compatible_path = self._ensure_qt_compatible_video(path)
        if compatible_path:
            path = compatible_path

        self.current_video_path = path
        self.media_player.setSource(QUrl.fromLocalFile(path))
        self._set_transport_enabled_state()
        self._set_status(f"Loaded video: {os.path.basename(path)}")

        if restore_position_ms > 0:
            QTimer.singleShot(400, lambda: self.media_player.setPosition(restore_position_ms))

        auto_srt = find_best_srt_for_video(path)
        if auto_srt:
            self._load_subtitles(auto_srt)
        else:
            self.subtitle_label.set_subtitle_text("")
            self.subtitle_label.show()
            self.subtitle_parser = None
            self.current_srt_path = ""
            self._prompt_generate_subtitles()

        self._persist_last_session()

    def _ensure_qt_compatible_video(self, path):
        codec = self._probe_video_codec(path)
        if codec != "av1":
            return None

        target_path = str(Path(path).with_name(f"{Path(path).stem}.qt_compatible.mp4"))
        if Path(target_path).exists():
            return target_path

        choice = QMessageBox.question(
            self,
            "AV1 Compatibility",
            (
                "This video uses AV1, which your Qt multimedia backend cannot decode on this system.\n\n"
                "Create a compatible H.264 copy now?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return None

        self._set_status("Converting video to H.264 for compatibility. This may take a while...", 10000)
        try:
            self._transcode_video_for_qt(path, target_path)
            self._set_status(f"Conversion complete: {os.path.basename(target_path)}", 5000)
            return target_path
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Conversion Failed",
                f"Could not convert AV1 video to a compatible format:\n{exc}",
            )
            return None

    def _probe_video_codec(self, path):
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return (result.stdout or "").strip().lower()
        except Exception:
            return ""

    def _transcode_video_for_qt(self, input_path, output_path):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                input_path,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                output_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def _prompt_generate_subtitles(self):
        if not self.current_video_path:
            return

        choice = QMessageBox.question(
            self,
            "Subtitles Not Found",
            "No matching .srt file was found. Generate subtitles now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if choice == QMessageBox.StandardButton.Yes:
            self._generate_subtitles_interactive()

    def _generate_subtitles_interactive(self):
        if not self.current_video_path:
            QMessageBox.information(self, "No Video", "Open a video file first.")
            return

        dialog = SubtitleGeneratorDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        model = dialog.selected_model()
        language = dialog.selected_language()
        dialog.status_label.setText("Starting generation...")
        dialog.progress_bar.setVisible(True)

        worker = SubtitleGeneratorWorker(self.current_video_path, model, language)
        worker.signals.progress.connect(dialog.status_label.setText)

        def on_finished(srt_path):
            dialog.status_label.setText("Finished")
            self._load_subtitles(srt_path)
            self._set_status(f"Generated subtitles: {os.path.basename(srt_path)}", 4000)

        def on_failed(message):
            QMessageBox.critical(self, "Subtitle Generation Error", message)

        worker.signals.finished.connect(on_finished)
        worker.signals.failed.connect(on_failed)
        self._subtitle_thread_pool.start(worker)

    def _load_subtitles(self, srt_path):
        try:
            self.subtitle_parser = SRTParser.from_file(srt_path)
            self.current_srt_path = srt_path
            self._set_status(f"Loaded subtitles: {os.path.basename(srt_path)}")
            self._persist_last_session()
        except Exception as exc:
            QMessageBox.critical(self, "Subtitle Error", f"Failed to parse subtitles:\n{exc}")
            self.subtitle_parser = None
            self.current_srt_path = ""

    def _on_subtitle_click(self, word, modifiers):
        if not self.current_subtitle:
            return

        clean_word = self._clean_word(word)
        if not clean_word:
            return

        self.selected_word = clean_word
        self.selected_sentence = self.current_subtitle.text
        self.selected_translation = "Translating..."
        self._update_selection_panel()
        self._update_action_buttons()
        self.subtitle_label.highlight_word(clean_word)
        self._request_translation(clean_word)

    def _on_position_changed(self, position):
        if not self._is_slider_dragging:
            self.position_slider.setValue(position)

        duration = self.media_player.duration()
        time_text = f"{self._fmt_ms(position)} / {self._fmt_ms(duration)}"
        self.time_label.setText(time_text)

        if not self.subtitle_parser:
            self.current_subtitle = None
            self.subtitle_label.set_subtitle_text("")
            self.subtitle_label.show()
            return

        lookup_position = max(0, position - self.subtitle_offset_ms)
        subtitle = self.subtitle_parser.get_subtitle_at_time(lookup_position)
        if subtitle is None:
            self.current_subtitle = None
            self.subtitle_label.set_subtitle_text("")
            self.subtitle_label.show()
            return

        if self.current_subtitle is None or subtitle.index != self.current_subtitle.index:
            self.current_subtitle = subtitle
            self.subtitle_label.set_subtitle_text(subtitle.text)
            self.subtitle_label.show()

    def _on_duration_changed(self, duration):
        self.position_slider.setRange(0, max(0, duration))
        time_text = f"00:00 / {self._fmt_ms(duration)}"
        self.time_label.setText(time_text)

    def _on_playback_state_changed(self, state):
        self._set_transport_enabled_state()

    def _set_transport_enabled_state(self):
        if not self.media_player:
            return
        is_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        icon_text = "⏸️" if is_playing else "▶️"
        if self.play_pause_button:
            self.play_pause_button.setText(icon_text)
        if self.play_pause_toolbar_action:
            self.play_pause_toolbar_action.setText(icon_text)

    def _toggle_play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _seek_relative(self, delta_ms):
        current = self.media_player.position()
        target = max(0, min(self.media_player.duration(), current + delta_ms))
        self.media_player.setPosition(target)

    def _adjust_subtitle_offset(self, delta_ms):
        self.subtitle_offset_ms += delta_ms
        seconds = self.subtitle_offset_ms / 1000.0
        if self.subtitle_offset_label:
            self.subtitle_offset_label.setText(f"Offset: {seconds:+.2f}s")
        self._set_status(f"Subtitle timing offset: {seconds:+.2f}s", 1500)

    def _on_slider_pressed(self):
        self._is_slider_dragging = True

    def _on_slider_released(self):
        self._is_slider_dragging = False
        self.media_player.setPosition(self.position_slider.value())

    def _on_slider_moved(self, value):
        duration = self.media_player.duration()
        time_text = f"{self._fmt_ms(value)} / {self._fmt_ms(duration)}"
        self.time_label.setText(time_text)

    def _set_video_speed(self, speed):
        self.media_player.setPlaybackRate(speed)
        self.user_data["preferences"]["video_playback_speed"] = speed
        self._save_user_data()
        if self.speed_menu_actions:
            for candidate, action in self.speed_menu_actions.items():
                action.setChecked(abs(candidate - speed) < 1e-9)

    def _fmt_ms(self, ms):
        total_sec = max(0, int(ms // 1000))
        m, s = divmod(total_sec, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"

    def _restore_session_state(self):
        last_session = self.user_data.get("last_session", {})
        video_path = str(last_session.get("video_path") or "")
        position = int(last_session.get("video_position_ms") or 0)
        srt_path = str(last_session.get("srt_path") or "")

        speed = float(self.user_data.get("preferences", {}).get("video_playback_speed", 1.0))
        if speed not in self.speed_menu_actions:
            speed = 1.0
        self._set_video_speed(speed)

        if video_path and Path(video_path).exists():
            self._load_video(video_path, restore_position_ms=position)
            if srt_path and Path(srt_path).exists():
                self._load_subtitles(srt_path)

    def _persist_last_session(self):
        self.user_data["mode"] = "video"
        self.user_data["last_session"]["video_path"] = self.current_video_path
        self.user_data["last_session"]["video_position_ms"] = int(self.media_player.position() if self.media_player else 0)
        self.user_data["last_session"]["srt_path"] = self.current_srt_path
        self._save_user_data()

    def _clear_viewer_state(self):
        self._clear_selection_state()
        self.current_subtitle = None
        if self.subtitle_label:
            self.subtitle_label.set_subtitle_text("")
            self.subtitle_label.show()

    def closeEvent(self, event):
        self._persist_last_session()
        super().closeEvent(event)
