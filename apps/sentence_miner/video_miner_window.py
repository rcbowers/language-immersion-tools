#!/usr/bin/env python3
"""Video sentence miner window."""

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSizePolicy,
    QTextEdit,
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
    def __init__(self, parent=None, default_language="es"):
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
        self.language_input = QLineEdit(default_language or "es")
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
        self.video_container = None
        self.transport_overlay = None

        self.subtitle_label = None
        self.subtitle_parser = None
        self.current_subtitle = None
        self.subtitle_selection_anchor = None

        self.current_video_path = ""
        self.current_srt_path = ""

        self.play_pause_button = None
        self.play_pause_toolbar_action = None
        self.position_slider = None
        self.subtitle_offset_label = None
        self.subtitle_debug_bounds_value = None
        self.subtitle_debug_click_value = None
        self.time_label = None
        self.speed_action_group = None
        self.speed_menu_actions = {}
        self._is_slider_dragging = False
        self.subtitle_offset_ms = 0
        self._session_timer = QTimer()
        self._session_timer.setInterval(5000)
        self._transport_hide_timer = QTimer()
        self._transport_hide_timer.setSingleShot(True)
        self._transport_hide_timer.setInterval(700)

        self._subtitle_thread_pool = QThreadPool.globalInstance()

        super().__init__("Spanish Video Sentence Miner")
        self._add_video_debug_status_to_right_panel()

        self._transport_hide_timer.timeout.connect(self._hide_transport_overlay_if_idle)
        self._session_timer.timeout.connect(self._persist_last_session)
        self._session_timer.start()

    def _add_video_debug_status_to_right_panel(self):
        if not self.right_panel:
            return
        layout = self.right_panel.layout()
        if not layout:
            return

        self.subtitle_offset_label = QLabel("Offset: +0.00s")
        self.subtitle_debug_bounds_value = QTextEdit()
        self.subtitle_debug_bounds_value.setReadOnly(True)
        self.subtitle_debug_bounds_value.setFixedHeight(180)
        self.subtitle_debug_click_value = QTextEdit()
        self.subtitle_debug_click_value.setReadOnly(True)
        self.subtitle_debug_click_value.setFixedHeight(72)

        debug_group = QGroupBox("Subtitle Debug")
        debug_layout = QVBoxLayout(debug_group)
        debug_layout.addWidget(QLabel("Current Subtitle Word Bounds"))
        debug_layout.addWidget(self.subtitle_debug_bounds_value)
        debug_layout.addWidget(QLabel("Last Subtitle Click"))
        debug_layout.addWidget(self.subtitle_debug_click_value)

        insert_index = layout.count()
        if self.mode_indicator_label:
            mode_idx = layout.indexOf(self.mode_indicator_label)
            if mode_idx >= 0:
                insert_index = mode_idx + 1
        layout.insertWidget(insert_index, self.subtitle_offset_label)
        layout.insertWidget(insert_index + 1, debug_group)
        self._refresh_subtitle_debug_bounds()
        self._record_subtitle_click_debug(None)

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

        self.video_container = QWidget(panel)
        self.video_container.setMinimumHeight(480)
        self.video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_container.setMouseTracking(True)
        self.video_container.installEventFilter(self)
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget(self.video_container)
        self.video_widget.setMinimumHeight(480)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_widget.setMouseTracking(True)
        self.video_widget.installEventFilter(self)
        video_layout.addWidget(self.video_widget, stretch=1)

        self.transport_overlay = QWidget(self, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.transport_overlay.setObjectName("transportOverlay")
        self.transport_overlay.setStyleSheet(
            "#transportOverlay {"
            "background-color: rgba(140, 140, 140, 210);"
            "border-radius: 10px;"
            "}"
        )
        self.transport_overlay.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.transport_overlay.hide()
        self.transport_overlay.setMouseTracking(True)
        self.transport_overlay.installEventFilter(self)
        timeline_layout = QHBoxLayout(self.transport_overlay)
        timeline_layout.setContentsMargins(12, 4, 12, 4)
        timeline_layout.setSpacing(8)
        self.play_pause_button = QPushButton("▶")
        self.play_pause_button.setMinimumWidth(42)
        self.play_pause_button.setToolTip("Play/Pause")
        self.play_pause_button.clicked.connect(self._toggle_play_pause)
        self.play_pause_button.installEventFilter(self)
        timeline_layout.addWidget(self.play_pause_button)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.setMouseTracking(True)
        self.position_slider.installEventFilter(self)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        timeline_layout.addWidget(self.position_slider, stretch=1)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.installEventFilter(self)
        timeline_layout.addWidget(self.time_label)
        layout.addWidget(self.video_container, stretch=1)

        self.subtitle_label = ClickableSubtitleLabel(panel)
        self.subtitle_label.setFixedHeight(96)
        self.subtitle_label.set_subtitle(None)
        self.subtitle_label.show()
        self.subtitle_label.clicked.connect(self._on_subtitle_click)
        self.subtitle_label.debug_clicked.connect(self._record_subtitle_click_debug)
        self.subtitle_label.layout_updated.connect(self._refresh_subtitle_debug_bounds)
        layout.addWidget(self.subtitle_label)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)

        self._set_transport_enabled_state()
        QTimer.singleShot(0, self._stabilize_video_layout)
        return panel

    def _stabilize_video_layout(self):
        self._position_transport_overlay()
        if self.position_slider:
            self.position_slider.updateGeometry()
        if self.time_label:
            self.time_label.updateGeometry()
        central = self.centralWidget()
        if central:
            central.updateGeometry()
            central.update()

    def eventFilter(self, watched, event):
        transport_widgets = {
            self.video_container,
            self.video_widget,
            self.transport_overlay,
            self.play_pause_button,
            self.position_slider,
            self.time_label,
        }
        if watched in transport_widgets:
            widget_name = self._transport_debug_widget_name(watched)
            if event.type() == QEvent.Type.Resize and watched == self.video_container:
                print(f"[transport-debug] resize on {widget_name}: size={self.video_container.size()}")
                self._position_transport_overlay()
            elif event.type() in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
                print(f"[transport-debug] enter on {widget_name}")
                self._show_transport_overlay()
            elif event.type() == QEvent.Type.MouseMove:
                print(f"[transport-debug] mouse move on {widget_name}")
                self._show_transport_overlay()
            elif event.type() == QEvent.Type.Leave:
                print(f"[transport-debug] leave on {widget_name}")
                self._schedule_transport_overlay_hide()
        return super().eventFilter(watched, event)

    def _position_transport_overlay(self):
        if not self.video_container or not self.transport_overlay:
            return

        self.transport_overlay.adjustSize()
        container_top_left = self.video_container.mapToGlobal(self.video_container.rect().topLeft())
        margin = 16
        max_width = max(240, self.video_container.width() - (margin * 2))
        overlay_width = min(max_width, 560)
        overlay_height = self.transport_overlay.sizeHint().height()
        x = container_top_left.x() + max(margin, (self.video_container.width() - overlay_width) // 2)
        y = container_top_left.y() + max(margin, self.video_container.height() - overlay_height - margin)
        self.transport_overlay.setGeometry(x, y, overlay_width, overlay_height)
        self.transport_overlay.raise_()
        print(
            "[transport-debug] position overlay:",
            f"container_top_left=({container_top_left.x()}, {container_top_left.y()})",
            f"container_size=({self.video_container.width()}x{self.video_container.height()})",
            f"overlay_geometry={self.transport_overlay.geometry()}",
        )

    def _show_transport_overlay(self):
        if not self.transport_overlay:
            return
        self._transport_hide_timer.stop()
        self._position_transport_overlay()
        self.transport_overlay.show()
        self.transport_overlay.raise_()
        print(
            "[transport-debug] show overlay:",
            f"visible={self.transport_overlay.isVisible()}",
            f"geometry={self.transport_overlay.geometry()}",
        )

    def _schedule_transport_overlay_hide(self):
        if not self.transport_overlay or self._is_slider_dragging:
            print(
                "[transport-debug] skip schedule hide:",
                f"has_overlay={bool(self.transport_overlay)}",
                f"is_slider_dragging={self._is_slider_dragging}",
            )
            return
        print("[transport-debug] schedule hide")
        self._transport_hide_timer.start()

    def _hide_transport_overlay_if_idle(self):
        if not self.transport_overlay or self._is_slider_dragging:
            print(
                "[transport-debug] skip hide:",
                f"has_overlay={bool(self.transport_overlay)}",
                f"is_slider_dragging={self._is_slider_dragging}",
            )
            return
        if any(
            widget and widget.underMouse()
            for widget in (
                self.video_container,
                self.video_widget,
                self.transport_overlay,
                self.play_pause_button,
                self.position_slider,
                self.time_label,
            )
        ):
            print("[transport-debug] keep overlay visible because pointer is still over transport/video")
            return
        self.transport_overlay.hide()
        print("[transport-debug] hide overlay")

    def _transport_debug_widget_name(self, widget):
        if widget is self.video_container:
            return "video_container"
        if widget is self.video_widget:
            return "video_widget"
        if widget is self.transport_overlay:
            return "transport_overlay"
        if widget is self.play_pause_button:
            return "play_pause_button"
        if widget is self.position_slider:
            return "position_slider"
        if widget is self.time_label:
            return "time_label"
        return type(widget).__name__

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.transport_overlay and self.transport_overlay.isVisible():
            self._position_transport_overlay()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.transport_overlay and self.transport_overlay.isVisible():
            self._position_transport_overlay()

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
            self.subtitle_label.set_subtitle(None)
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

        dialog = SubtitleGeneratorDialog(self, default_language=self._get_whisper_learning_language())
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
            self._refresh_subtitle_debug_bounds()
            self._persist_last_session()
        except Exception as exc:
            QMessageBox.critical(self, "Subtitle Error", f"Failed to parse subtitles:\n{exc}")
            self.subtitle_parser = None
            self.current_srt_path = ""
            self._refresh_subtitle_debug_bounds()

    def _on_subtitle_click(self, word, token_index, modifiers):
        if not self.current_subtitle:
            return

        words = self.current_subtitle.words
        if token_index < 0 or token_index >= len(words):
            return

        shift_pressed = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        selected_indices = self._resolve_selected_subtitle_indices(token_index, shift_pressed, len(words))

        cleaned_words = []
        for idx in selected_indices:
            cleaned = self._clean_word(words[idx].word)
            if cleaned:
                cleaned_words.append(cleaned)

        if not cleaned_words:
            return

        self.selected_word = " ".join(cleaned_words)
        self.selected_sentence = self.current_subtitle.text
        self.selected_translation = "Translating..."
        self._update_selection_panel()
        self._update_action_buttons()
        self.subtitle_label.highlight_word_range(selected_indices[0], selected_indices[-1])
        self._request_translation(self.selected_word)

    def _resolve_selected_subtitle_indices(self, token_index, shift_pressed, token_count):
        subtitle_index = self.current_subtitle.index if self.current_subtitle else -1
        if (
            not shift_pressed
            or self.subtitle_selection_anchor is None
            or self.subtitle_selection_anchor[0] != subtitle_index
        ):
            self.subtitle_selection_anchor = (subtitle_index, token_index)
            return [token_index]

        anchor_index = self.subtitle_selection_anchor[1]
        anchor_index = max(0, min(anchor_index, token_count - 1))
        start = min(anchor_index, token_index)
        end = max(anchor_index, token_index)
        return list(range(start, end + 1))

    def _on_position_changed(self, position):
        if not self._is_slider_dragging:
            self.position_slider.setValue(position)

        duration = self.media_player.duration()
        time_text = f"{self._fmt_ms(position)} / {self._fmt_ms(duration)}"
        self.time_label.setText(time_text)
        self._refresh_subtitle_for_position(position)

    def _refresh_subtitle_for_position(self, position):
        if not self.subtitle_parser:
            self.current_subtitle = None
            self.subtitle_selection_anchor = None
            self.subtitle_label.set_subtitle(None)
            self.subtitle_label.show()
            self._refresh_subtitle_debug_bounds()
            return
        lookup_position = max(0, position - self.subtitle_offset_ms)
        subtitle = self.subtitle_parser.get_subtitle_at_time(lookup_position)
        if subtitle is None:
            self.current_subtitle = None
            self.subtitle_selection_anchor = None
            self.subtitle_label.set_subtitle(None)
            self.subtitle_label.show()
            self._refresh_subtitle_debug_bounds()
            return

        if self.current_subtitle is None or subtitle.index != self.current_subtitle.index:
            self.current_subtitle = subtitle
            self.subtitle_selection_anchor = None
            self.subtitle_label.set_subtitle(subtitle)
            self.subtitle_label.show()
            self._refresh_subtitle_debug_bounds()

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
        icon_text = "⏸" if is_playing else "▶"
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
        self._refresh_subtitle_for_position(self.media_player.position())

    def _on_slider_pressed(self):
        self._is_slider_dragging = True
        self._show_transport_overlay()

    def _on_slider_released(self):
        self._is_slider_dragging = False
        self.media_player.setPosition(self.position_slider.value())
        self._schedule_transport_overlay_hide()

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
        self.subtitle_selection_anchor = None
        if self.subtitle_label:
            self.subtitle_label.set_subtitle(None)
            self.subtitle_label.show()
        self._refresh_subtitle_debug_bounds()
        self._record_subtitle_click_debug(None)

    def _refresh_subtitle_debug_bounds(self):
        if not self.subtitle_debug_bounds_value:
            return

        if not self.current_subtitle or not self.subtitle_label:
            self.subtitle_debug_bounds_value.setPlainText("No active subtitle.")
            return

        lines = []
        for entry in self.subtitle_label.get_word_debug_bounds():
            rect_text = ", ".join(self._format_debug_rect(rect) for rect in entry["rects"]) or "no rects"
            lines.append(f"[{entry['index']}] {entry['word']}: {rect_text}")
        self.subtitle_debug_bounds_value.setPlainText("\n".join(lines) or "No active subtitle.")

    def _record_subtitle_click_debug(self, payload):
        if not self.subtitle_debug_click_value:
            return
        if not payload:
            self.subtitle_debug_click_value.setPlainText("No subtitle click recorded.")
            return

        coords = f"widget=({payload['x']:.1f}, {payload['y']:.1f})"
        if payload.get("index") is None:
            self.subtitle_debug_click_value.setPlainText(f"{coords}\nresult=miss")
            return

        self.subtitle_debug_click_value.setPlainText(
            f"{coords}\nresult=hit [{payload['index']}] {payload['word']}"
        )

    def _format_debug_rect(self, rect):
        return (
            f"(x={rect['x']:.1f}, y={rect['y']:.1f}, "
            f"w={rect['width']:.1f}, h={rect['height']:.1f})"
        )

    def closeEvent(self, event):
        if self.transport_overlay:
            self.transport_overlay.hide()
        self._persist_last_session()
        super().closeEvent(event)
