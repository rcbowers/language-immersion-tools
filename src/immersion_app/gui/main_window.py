"""Unified sentence mining workspace."""

from __future__ import annotations

import logging
import os
import re
import socket
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

import fitz
from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence, QPainter, QPen, QPixmap, QTextCursor
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from immersion_app.core.anki import add_anki_card, fetch_deck_words, test_anki_connection
from immersion_app.core.anki_snapshot import load_snapshot, save_snapshot
from immersion_app.core.language_config import (
    DEFAULT_LEARNING_LANGUAGE,
    DEFAULT_NATIVE_LANGUAGE,
    get_argos_language_code,
    get_google_language_code,
    get_language_label,
    get_marian_language_code,
    get_whisper_language_code,
    list_language_codes,
    normalize_language_code,
)
from immersion_app.core.mode import WorkspaceMode, ModeManager
from immersion_app.core.selection_state import SelectionState
from immersion_app.core.shortcuts import ShortcutManager
from immersion_app.core.paths import DATA_ROOT, PROCESSED_LOG_PATH, QUEUE_JSON_PATH
from immersion_app.core.queue_store import append_processed_log, append_queue_entry, load_queue_entries, queue_count, save_queue_entries
from immersion_app.core.user_data import load_user_data, save_user_data
from immersion_app.gui.widgets.card_feedback_toast import CardFeedbackToast
from immersion_app.gui.widgets.subtitle_widget import ClickableSubtitleLabel
from immersion_app.gui.widgets.command_bar import CommandBar
from immersion_app.gui.widgets.translation_popover import TranslationPopover
from immersion_app.gui.widgets.pdf_status_bar import PDFStatusBar
from immersion_app.gui.widgets.transport_bar import TransportBar
from immersion_app.gui.theme import Theme
from immersion_app.integrations.subtitle_generation import generate_srt_from_video
from immersion_app.integrations.translation_backends import MarianMTTranslationBackend, OnlineTranslationBackend
from immersion_app.media.subtitle_matching import find_best_srt_for_video
from immersion_app.media.subtitle_parser import SRTParser

ANKI_PATH = r"C:\Program Files\Anki\anki.exe"


class TranslateSignals(QObject):
    finished = Signal(int, str, str)
    failed = Signal(int, str)


class TranslateTask(QRunnable):
    def __init__(self, request_id, text, src_lang, dest_lang, backend):
        super().__init__()
        self.request_id = request_id
        self.text = text
        self.src_lang = src_lang
        self.dest_lang = dest_lang
        self.backend = backend
        self.signals = TranslateSignals()

    def run(self):
        try:
            translated_text = self.backend.translate(self.text, self.src_lang, self.dest_lang)
            try:
                self.signals.finished.emit(self.request_id, self.text, translated_text)
            except RuntimeError:
                return
        except Exception as exc:
            logger.error(f"Translation worker failed (request_id={self.request_id}): {exc}", exc_info=True)
            try:
                self.signals.failed.emit(self.request_id, str(exc))
            except RuntimeError:
                return


class BatchTranslateSignals(QObject):
    finished = Signal(list, list)  # (texts, translations)
    failed = Signal(str)  # error message


class BatchTranslateTask(QRunnable):
    """Task for translating multiple texts in a single batch request."""

    def __init__(self, texts, src_lang, dest_lang, backend):
        super().__init__()
        self.texts = texts
        self.src_lang = src_lang
        self.dest_lang = dest_lang
        self.backend = backend
        self.signals = BatchTranslateSignals()

    def run(self):
        try:
            # Use batch translation if backend supports it
            if hasattr(self.backend, 'translate_batch'):
                translations = self.backend.translate_batch(self.texts, self.src_lang, self.dest_lang)
            else:
                # Fallback: translate one by one
                translations = [self.backend.translate(text, self.src_lang, self.dest_lang) for text in self.texts]

            try:
                self.signals.finished.emit(self.texts, translations)
            except RuntimeError:
                return
        except Exception as exc:
            logger.error(f"Batch translation worker failed ({len(self.texts)} texts): {exc}", exc_info=True)
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                return


class AnkiStatusSignals(QObject):
    finished = Signal(int, bool, object)


class AnkiStatusTask(QRunnable):
    def __init__(self, request_id):
        super().__init__()
        self.request_id = request_id
        self.signals = AnkiStatusSignals()

    def run(self):
        try:
            connected = test_anki_connection()
            words = fetch_deck_words() if connected else None
            self.signals.finished.emit(self.request_id, connected, words)
        except RuntimeError:
            return


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
            try:
                self.signals.finished.emit(path)
            except RuntimeError:
                return
        except Exception as exc:
            logger.error(f"Subtitle generation worker failed for {self.video_path}: {exc}", exc_info=True)
            try:
                self.signals.failed.emit(str(exc))
            except RuntimeError:
                return


class ClickablePdfLabel(QLabel):
    clicked = Signal(QPoint, object)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(event.position().toPoint(), event.modifiers())
        super().mousePressEvent(event)


class SubtitleGeneratorDialog(QDialog):
    def __init__(self, parent=None, default_language="es"):
        super().__init__(parent)
        self.setWindowTitle("Generate Subtitles")
        self.resize(420, 220)
        self.setStyleSheet(f"QDialog {{ background-color: {Theme.BG}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        model_row = QHBoxLayout()
        model_label = QLabel("Model:")
        model_label.setStyleSheet(Theme.get_label_style("body"))
        model_row.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium"])
        self.model_combo.setCurrentText("base")
        model_row.addWidget(self.model_combo)
        layout.addLayout(model_row)

        language_row = QHBoxLayout()
        lang_label = QLabel("Language:")
        lang_label.setStyleSheet(Theme.get_label_style("body"))
        language_row.addWidget(lang_label)
        self.language_input = QLineEdit(default_language or "es")
        self.language_input.setStyleSheet(Theme.get_input_style())
        language_row.addWidget(self.language_input)
        layout.addLayout(language_row)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(Theme.get_label_style("caption"))
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        start_button = QPushButton("Generate")
        start_button.setStyleSheet(Theme.get_button_style("primary"))
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet(Theme.get_button_style("secondary"))
        start_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(start_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

    def selected_model(self):
        return self.model_combo.currentText()

    def selected_language(self):
        return self.language_input.text().strip() or "es"


class QueueDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Queued Cards")
        self.resize(620, 420)
        self.setStyleSheet(f"QDialog {{ background-color: {Theme.BG}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet(Theme.get_label_style("body"))
        layout.addWidget(self.summary_label)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 8px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {Theme.SURFACE_ALT};
            }}
        """)
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        self.process_button = QPushButton("Process Queue")
        self.process_button.setStyleSheet(Theme.get_button_style("primary"))
        close_button = QPushButton("Close")
        close_button.setStyleSheet(Theme.get_button_style("secondary"))
        close_button.clicked.connect(self.accept)
        button_row.addWidget(self.process_button)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

    def refresh(self, entries):
        self.list_widget.clear()
        self.summary_label.setText(f"Queued cards: {len(entries)} | Storage: {QUEUE_JSON_PATH}")
        for entry in entries:
            self.list_widget.addItem(
                f"{entry.get('word', '')} | {entry.get('source_name', 'unknown')} | {entry.get('location', '')}"
            )


class UnifiedSentenceMinerWindow(QMainWindow):
    SUPPORTED_CONTENT_FILTER = "Content Files (*.pdf *.mp4 *.mkv *.avi *.mov *.webm)"

    def __init__(self, console_capture=None):
        super().__init__()
        self.setWindowTitle("LinguaLoop Workspace")
        self.resize(1680, 980)

        self.thread_pool = QThreadPool.globalInstance()
        self._subtitle_thread_pool = QThreadPool.globalInstance()
        self.current_request_id = 0
        self._next_translation_request_id = 0
        self.anki_check_request_id = 0
        self.translation_cache = {}
        self._translation_requests = {}
        self._translation_requests_by_key = {}
        self._translation_context_version = 0
        self._online_backend = None
        self._offline_backend = None
        self._cache_hits = 0
        self._cache_misses = 0
        self.console_capture = console_capture
        self.user_data = load_user_data()
        self.analytics_vocabulary = set(self.user_data.get("analytics", {}).get("vocabulary_seen", []))
        snapshot_words = load_snapshot()
        self.analytics_vocabulary.update(snapshot_words)
        logger.info(f"Analytics vocabulary initialized with {len(self.analytics_vocabulary)} words ({len(snapshot_words)} from snapshot)")

        # Log startup configuration
        logger.info("=" * 60)
        logger.info("LinguaLoop Workspace - Application Startup")
        logger.info("=" * 60)
        logger.info(f"Learning Language: {self.user_data['preferences']['learning_language']}")
        logger.info(f"Native Language: {self.user_data['preferences']['native_language']}")
        logger.info(f"Translation Mode: {self.user_data['preferences']['translation_mode']}")
        logger.info(f"Video Playback Speed: {self.user_data['preferences']['video_playback_speed']}x")
        logger.info(f"Recent Files: {len(self.user_data['recent_files'])} file(s)")
        logger.info(f"Total Cards Added: {self.user_data['analytics']['cards_added_total']}")
        logger.info(f"Vocabulary Seen: {len(self.user_data['analytics'].get('vocabulary_seen', []))} words")
        logger.info("-" * 60)
        last_session = self.user_data['last_session']
        if last_session.get('content_type'):
            logger.info(f"Last Session Type: {last_session['content_type']}")
            if last_session.get('pdf_path'):
                logger.info(f"  PDF: {last_session['pdf_path']}")
                logger.info(f"  Page: {last_session.get('page_index', 0) + 1}")
            if last_session.get('video_path'):
                logger.info(f"  Video: {last_session['video_path']}")
                logger.info(f"  Position: {last_session.get('video_position_ms', 0) / 1000:.1f}s")
                if last_session.get('srt_path'):
                    logger.info(f"  Subtitles: {last_session['srt_path']}")
                    logger.info(f"  Subtitle Offset: {last_session.get('subtitle_offset_ms', 0)}ms")
        else:
            logger.info("Last Session: None (starting fresh)")
        logger.info("=" * 60)

        # Mode management
        self.mode_manager = ModeManager()
        self.selection = SelectionState()
        self.shortcut_manager = ShortcutManager()

        self.current_source_name = ""
        self.current_source_location = ""
        self.is_anki_connected = False
        self.translation_mode = self.user_data["preferences"].get("translation_mode", "offline")
        self.learning_language = self.user_data["preferences"].get("learning_language", DEFAULT_LEARNING_LANGUAGE)
        self.native_language = self.user_data["preferences"].get("native_language", DEFAULT_NATIVE_LANGUAGE)
        self.sentence_counts = {}
        self.anki_process = None

        self.doc = None
        self.current_pdf_path = ""
        self.current_page_index = 0
        self.zoom_factor = 2.0
        self.page_words = []
        self.page_line_words = {}
        self.page_word_order = []
        self.page_word_index = {}

        self.media_player = None
        self.audio_output = None
        self.current_video_path = ""
        self.current_srt_path = ""
        self.subtitle_parser = None
        self.current_subtitle = None
        self.subtitle_offset_ms = int(self.user_data["last_session"].get("subtitle_offset_ms") or 0)
        self._is_slider_dragging = False
        self._initial_layout_pending = True

        self.queue_dialog = None

        self._build_ui()
        self._determine_translation_mode()
        self._refresh_anki_status()
        self._restore_last_session()
        self._refresh_queue_summary()
        self._update_command_bar_stats()

    def _build_ui(self):
        # Create main container
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self._main_container = main_container
        self._main_layout = main_layout

        # Command bar at top
        self.command_bar = CommandBar(self.user_data)
        self.command_bar.open_requested.connect(self._open_content_dialog)
        self.command_bar.close_requested.connect(self._close_current_file)
        self.command_bar.settings_requested.connect(self._show_settings_dialog)
        self.command_bar.previous_page_requested.connect(self._prev_page)
        self.command_bar.next_page_requested.connect(self._next_page)
        self.command_bar.page_jump_requested.connect(self._jump_to_page)
        self.command_bar.recent_file_selected.connect(self._on_recent_file_selected)
        self.command_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        main_layout.addWidget(self.command_bar, stretch=0)

        # Workspace stack (Welcome/PDF/Video pages)
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.workspace_stack.setMinimumHeight(400)
        self.welcome_page = self._build_welcome_page()
        self.pdf_page = self._build_pdf_page()
        self.video_page = self._build_video_page()
        self.workspace_stack.addWidget(self.welcome_page)
        self.workspace_stack.addWidget(self.pdf_page)
        self.workspace_stack.addWidget(self.video_page)
        main_layout.addWidget(self.workspace_stack, stretch=1)

        self.console_pane = self._build_console_pane()
        self.console_pane.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        main_layout.addWidget(self.console_pane, stretch=0)

        self.setCentralWidget(main_container)

        # Apply background theme
        self.setStyleSheet(f"QMainWindow {{ background-color: {Theme.BG}; }}")

        # Initialize legacy widgets (temporary, will be removed with popover)
        self._init_legacy_widgets()

        # Create translation popover
        self.translation_popover = TranslationPopover(self)
        self.translation_popover.add_requested.connect(self._add_now)
        self.translation_popover.edit_requested.connect(self._on_popover_edit_requested)
        self.translation_popover.closed.connect(self._on_popover_closed)
        self.card_feedback_toast = CardFeedbackToast(self)

        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()

        # Connect mode manager signals
        self.mode_manager.mode_changed.connect(self._on_mode_changed_internal)
        self.mode_manager.mode_transition_failed.connect(self._on_mode_transition_failed)

    def resizeEvent(self, event):
        """Handle window resize - update layouts and reposition overlays."""
        super().resizeEvent(event)
        self._reposition_overlays()

    def changeEvent(self, event):
        """Handle window state changes (maximize/minimize/fullscreen)."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            # 50ms delay allows Qt to complete state transition
            QTimer.singleShot(50, self._reposition_overlays)

    def _reposition_overlays(self):
        """Reposition all floating overlays based on current window geometry."""
        self._position_card_feedback_toast()
        if self.translation_popover.isVisible():
            self.translation_popover.reposition_from_stored_anchor()

    def _setup_keyboard_shortcuts(self):
        """Setup mode-aware keyboard shortcuts."""
        # GLOBAL: File operations
        self._sc_open = QAction("Open source", self)
        self._sc_open.setShortcut(QKeySequence("Ctrl+O"))
        self._sc_open.triggered.connect(self._open_content_dialog)
        self.addAction(self._sc_open)
        self.shortcut_manager.add_shortcut('global', self._sc_open)

        self._sc_load_subs = QAction("Load subtitles", self)
        self._sc_load_subs.setShortcut(QKeySequence("Ctrl+L"))
        self._sc_load_subs.triggered.connect(self._open_subtitle_dialog)
        self.addAction(self._sc_load_subs)
        self.shortcut_manager.add_shortcut('global', self._sc_load_subs)

        # GLOBAL: Study actions
        self._sc_add_now = QAction("Add now", self)
        self._sc_add_now.setShortcut(QKeySequence("Ctrl+Return"))
        self._sc_add_now.triggered.connect(self._add_now)
        self.addAction(self._sc_add_now)
        self.shortcut_manager.add_shortcut('global', self._sc_add_now)

        self._sc_add_queue = QAction("Add to queue", self)
        self._sc_add_queue.setShortcut(QKeySequence("Ctrl+Shift+Return"))
        self._sc_add_queue.triggered.connect(self._add_to_queue)
        self.addAction(self._sc_add_queue)
        self.shortcut_manager.add_shortcut('global', self._sc_add_queue)

        # GLOBAL: Close popover
        escape_action = QAction("Close Popover", self)
        escape_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        escape_action.triggered.connect(self._close_popover)
        self.addAction(escape_action)
        self.shortcut_manager.add_shortcut('global', escape_action)

        # VIDEO: Playback
        play_action = QAction("Play/Pause", self)
        play_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        play_action.triggered.connect(self._toggle_play_pause)
        self.addAction(play_action)
        self.shortcut_manager.add_shortcut('video', play_action)

        # PDF: Navigation
        prev_page_action = QAction("Previous Page", self)
        prev_page_action.setShortcut(QKeySequence(Qt.Key.Key_Left))
        prev_page_action.triggered.connect(self._prev_page)
        self.addAction(prev_page_action)
        self.shortcut_manager.add_shortcut('pdf', prev_page_action)

        next_page_action = QAction("Next Page", self)
        next_page_action.setShortcut(QKeySequence(Qt.Key.Key_Right))
        next_page_action.triggered.connect(self._next_page)
        self.addAction(next_page_action)
        self.shortcut_manager.add_shortcut('pdf', next_page_action)

        # PDF: Zoom
        self._sc_zoom_in = QAction("Zoom In", self)
        self._sc_zoom_in.setShortcut(QKeySequence("Ctrl++"))
        self._sc_zoom_in.triggered.connect(self._zoom_in)
        self.addAction(self._sc_zoom_in)
        self.shortcut_manager.add_shortcut('pdf', self._sc_zoom_in)

        self._sc_zoom_out = QAction("Zoom Out", self)
        self._sc_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self._sc_zoom_out.triggered.connect(self._zoom_out)
        self.addAction(self._sc_zoom_out)
        self.shortcut_manager.add_shortcut('pdf', self._sc_zoom_out)

        self._sc_fit_width = QAction("Fit to Width", self)
        self._sc_fit_width.setShortcut(QKeySequence("Ctrl+0"))
        self._sc_fit_width.triggered.connect(self._fit_width)
        self.addAction(self._sc_fit_width)
        self.shortcut_manager.add_shortcut('pdf', self._sc_fit_width)

    def _build_console_pane(self):
        pane = QWidget()
        pane.setVisible(False)
        pane.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.SURFACE};
                border-top: 1px solid {Theme.BORDER};
            }}
        """)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(12, 6, 12, 8)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        title = QLabel("Python Console")
        title.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12px;
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
            }}
        """)
        header_row.addWidget(title)
        header_row.addStretch()

        close_button = QPushButton("Hide")
        close_button.setFixedHeight(24)
        close_button.setStyleSheet(Theme.get_button_style("secondary"))
        close_button.clicked.connect(lambda: self._toggle_console_pane(False))
        header_row.addWidget(close_button)
        layout.addLayout(header_row)

        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setMinimumHeight(160)
        self.console_output.setMaximumHeight(400)
        self.console_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.console_output.setStyleSheet(f"""
            QTextEdit {{
                background-color: #111827;
                color: #e4e4e7;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 8px;
                padding: 10px;
                font-family: {Theme.FONT_MONO};
                font-size: 12px;
            }}
        """)
        layout.addWidget(self.console_output)
        return pane

    def connect_console_capture(self):
        if self.console_capture is None:
            return
        self.console_capture.text_emitted.connect(self._append_console_text)

    def _toggle_console_pane(self, checked=None):
        if checked is None:
            checked = not self.console_pane.isVisible()
        checked = bool(checked)
        self.console_pane.setVisible(checked)
        if hasattr(self, "pdf_status_bar"):
            self.pdf_status_bar.set_console_visible(checked)
        if checked:
            self.console_output.moveCursor(QTextCursor.MoveOperation.End)

    def _append_console_text(self, text):
        if not text:
            return
        cursor = self.console_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.console_output.setTextCursor(cursor)
        self.console_output.ensureCursorVisible()
        document = self.console_output.document()
        max_blocks = 3000
        while document.blockCount() > max_blocks:
            trim_cursor = self.console_output.textCursor()
            trim_cursor.movePosition(QTextCursor.MoveOperation.Start)
            trim_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            trim_cursor.removeSelectedText()
            trim_cursor.deleteChar()

    def _on_recent_file_selected(self, file_path: str, file_type: str):
        """
        Handle selection of a recent file.

        Args:
            file_path: Absolute path to the file
            file_type: "pdf" or "video"
        """
        path = Path(file_path)

        # Validate file exists
        if not path.exists():
            QMessageBox.critical(
                self,
                "File Not Found",
                f"The file no longer exists:\n{file_path}\n\nIt may have been moved or deleted."
            )
            # Remove from recent files
            from immersion_app.core.recent_files import remove_recent_file
            remove_recent_file(self.user_data, file_path)
            save_user_data(self.user_data)

            # Refresh recent files display
            if hasattr(self, 'welcome_recent_files_list'):
                self.welcome_recent_files_list.refresh()
            return

        # Get the stored position from recent files
        from immersion_app.core.recent_files import get_recent_files
        recent_files = get_recent_files(self.user_data, validate_exists=False)

        # Find the matching file entry to get its position
        file_entry = None
        normalized_path = os.path.normcase(os.path.abspath(file_path))
        for entry in recent_files:
            entry_path = os.path.normcase(os.path.abspath(entry.get("path", "")))
            if entry_path == normalized_path:
                file_entry = entry
                break

        # Load the file with stored position (auto-switches mode)
        if file_type == "pdf":
            page_index = file_entry.get("page_index", 0) if file_entry else 0
            self._load_pdf(str(path), initial_page_index=page_index)
        else:
            position_ms = file_entry.get("video_position_ms", 0) if file_entry else 0
            self._load_video(str(path), restore_position_ms=position_ms)

    def _on_mode_changed_internal(self, mode: WorkspaceMode):
        """
        Internal mode change handler - SINGLE PLACE for mode changes.
        """
        logger.info(f"Mode changed to {mode}")
        # Update workspace stack
        if mode == WorkspaceMode.WELCOME:
            self.workspace_stack.setCurrentWidget(self.welcome_page)
        elif mode == WorkspaceMode.PDF:
            self.workspace_stack.setCurrentWidget(self.pdf_page)
            if self.doc:
                self.command_bar.set_page_info(self.current_page_index + 1, self.doc.page_count)
        elif mode == WorkspaceMode.VIDEO:
            self.workspace_stack.setCurrentWidget(self.video_page)
            self.command_bar.set_page_info(0, 0)

        # Update keyboard shortcuts
        self.shortcut_manager.update_for_mode(mode)
        logger.debug(f"Keyboard shortcuts updated for mode {mode}")

    def _on_mode_transition_failed(self, mode_name: str, reason: str):
        """Handle failed mode transition."""
        self._set_status(f"Cannot switch to {mode_name}: {reason}")

    def _mode_to_string(self, mode: WorkspaceMode) -> str:
        """Convert WorkspaceMode to string for backward compatibility."""
        if mode == WorkspaceMode.PDF:
            return "pdf"
        elif mode == WorkspaceMode.VIDEO:
            return "video"
        return ""

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_layout_pending:
            self._initial_layout_pending = False
            self._reposition_overlays()

    def _show_settings_dialog(self):
        """Show settings dialog (stub for now - will implement later)."""
        # TODO: Create a proper settings dialog
        menu = QMenu(self)
        current_mode = self.mode_manager.current_mode

        menu.addAction("Toggle translation mode", self._toggle_translation_mode)
        menu.addSeparator()

        learning_menu = menu.addMenu("Learning language")
        learning_group = QActionGroup(self)
        learning_group.setExclusive(True)
        for code in list_language_codes():
            action = QAction(get_language_label(code), self)
            action.setCheckable(True)
            action.setChecked(code == self.learning_language)
            action.triggered.connect(lambda checked=False, lang_code=code: self._set_learning_language(lang_code))
            learning_group.addAction(action)
            learning_menu.addAction(action)

        native_menu = menu.addMenu("Native language")
        native_group = QActionGroup(self)
        native_group.setExclusive(True)
        for code in list_language_codes():
            action = QAction(get_language_label(code), self)
            action.setCheckable(True)
            action.setChecked(code == self.native_language)
            action.triggered.connect(lambda checked=False, lang_code=code: self._set_native_language(lang_code))
            native_group.addAction(action)
            native_menu.addAction(action)

        menu.addSeparator()
        menu.addAction("Start Anki", self._start_anki)
        menu.addAction("Check Anki", self._refresh_anki_status)

        # Only show subtitle generation in video mode
        if current_mode == WorkspaceMode.VIDEO:
            menu.addAction("Generate subtitles", self._generate_subtitles_interactive)

        menu.addSeparator()
        menu.addAction(self._sc_open)

        # Only show load subtitles in video mode
        if current_mode == WorkspaceMode.VIDEO:
            menu.addAction(self._sc_load_subs)

        menu.addSeparator()
        menu.addAction(self._sc_add_now)
        menu.addAction(self._sc_add_queue)

        # Only show zoom controls in PDF mode
        if current_mode == WorkspaceMode.PDF:
            menu.addSeparator()
            menu.addAction(self._sc_zoom_in)
            menu.addAction(self._sc_zoom_out)
            menu.addAction(self._sc_fit_width)

        # Show menu at settings button
        button_pos = self.command_bar.settings_button.mapToGlobal(
            self.command_bar.settings_button.rect().bottomLeft()
        )
        menu.exec(button_pos)

    def _build_welcome_page(self):
        """Build modern welcome page with themed styling."""
        page = QWidget()
        page.setStyleSheet(f"QWidget {{ background-color: {Theme.BG}; }}")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.addStretch(1)

        # Title
        title = QLabel("Open a PDF or video to start")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: {Theme.FONT_SIZE_TITLE};
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
                margin-bottom: 12px;
            }}
        """)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Click any word to see translations and build your vocabulary")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_SOFT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 15px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
                margin-bottom: 32px;
            }}
        """)
        layout.addWidget(subtitle)

        # Recent files section
        from immersion_app.gui.widgets.welcome_recent_files import WelcomeRecentFilesList
        recent_container = QWidget()
        recent_layout = QVBoxLayout(recent_container)
        recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.setSpacing(8)

        # Section heading
        recent_heading = QLabel("Recent")
        recent_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recent_heading.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 11px;
                font-weight: {Theme.FONT_WEIGHT_MEDIUM};
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 8px;
            }}
        """)
        recent_layout.addWidget(recent_heading)

        # Recent files list widget
        self.welcome_recent_files_list = WelcomeRecentFilesList(self.user_data)
        self.welcome_recent_files_list.file_selected.connect(self._on_recent_file_selected)
        recent_layout.addWidget(self.welcome_recent_files_list)

        layout.addWidget(recent_container)
        layout.addSpacing(24)

        # Buttons
        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        open_button = QPushButton("Open Source")
        open_button.setStyleSheet(Theme.get_button_style("primary"))
        open_button.setFixedHeight(40)
        open_button.setMinimumWidth(140)
        open_button.clicked.connect(self._open_content_dialog)
        button_row.addWidget(open_button)

        queue_button = QPushButton("View Queue")
        queue_button.setStyleSheet(Theme.get_button_style("secondary"))
        queue_button.setFixedHeight(40)
        queue_button.setMinimumWidth(140)
        queue_button.clicked.connect(self._show_queue_dialog)
        button_row.addWidget(queue_button)

        wrapper = QWidget()
        wrapper.setLayout(button_row)
        layout.addWidget(wrapper, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)

        # Keyboard shortcuts hint
        shortcuts = QLabel("Ctrl+O to open")
        shortcuts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shortcuts.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
                margin-top: 48px;
            }}
        """)
        layout.addWidget(shortcuts)

        return page

    def _init_legacy_widgets(self):
        """
        Create stub widgets that were previously in dock panels and status bar.
        These are kept temporarily to avoid breaking existing code.
        Will be removed once popover is fully integrated.
        """
        # Legacy widgets from source dock (hidden)
        self.source_summary_label = QLabel("No source loaded")
        self.queue_summary_label = QLabel()
        self.status_summary_label = QLabel()

        # Legacy widgets from inspector dock (hidden)
        self.source_header_label = QLabel("Nothing selected")
        self.word_value = QLineEdit()
        self.sentence_value = QTextEdit()
        self.translation_value = QTextEdit()
        self.add_now_button = QPushButton("Add Now")
        self.add_queue_button = QPushButton("Add to Queue")
        self.process_queue_button = QPushButton("Process Queue")
        self.mode_indicator_label = QLabel()
        self.subtitle_offset_label = QLabel("Subtitle Offset: +0.00s")
        self.health_label = QLabel()

        # Legacy widgets from status bar (hidden)
        self.translation_status_label = QLabel("Translation: checking...")
        self.anki_status_label = QLabel("Anki: checking...")

        # Connect legacy button signals (will be replaced by popover)
        self.add_now_button.clicked.connect(self._add_now)
        self.add_queue_button.clicked.connect(self._add_to_queue)
        self.process_queue_button.clicked.connect(self._process_queue)
        self.word_value.returnPressed.connect(self._translate_word_field_input)

    def _build_pdf_page(self):
        """Build PDF page with centered reading column layout."""
        page = QWidget()
        page.setStyleSheet(f"QWidget {{ background-color: {Theme.BG}; }}")

        # Overall layout: vertical stack
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        # Main horizontal layout: spacer | reading column | spacer | chapter rail
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Central reading column
        reading_column = QWidget()
        reading_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        column_layout = QVBoxLayout(reading_column)
        column_layout.setContentsMargins(36, 36, 36, 36)
        column_layout.setSpacing(0)

        # PDF scroll area
        self.pdf_label = ClickablePdfLabel()
        self.pdf_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.pdf_label.clicked.connect(self._on_pdf_click)
        self.pdf_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        self.pdf_label.setMinimumSize(400, 400)  # Prevent collapse
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.WheelFocus)
        self.scroll_area.setWidget(self.pdf_label)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {Theme.BG};
            }}
        """)
        column_layout.addWidget(self.scroll_area, stretch=1)

        main_layout.addWidget(reading_column, stretch=1)
        page_layout.addLayout(main_layout, stretch=1)

        # Status bar at bottom
        self.pdf_status_bar = PDFStatusBar()
        self.pdf_status_bar.zoom_in_clicked.connect(self._zoom_in)
        self.pdf_status_bar.zoom_out_clicked.connect(self._zoom_out)
        self.pdf_status_bar.fit_width_clicked.connect(self._fit_width)
        self.pdf_status_bar.reset_zoom_clicked.connect(self._reset_zoom)
        self.pdf_status_bar.console_toggled.connect(self._toggle_console_pane)
        page_layout.addWidget(self.pdf_status_bar)

        return page

    def _build_video_page(self):
        """Build video page with full-bleed layout and overlay subtitles."""
        page = QWidget()
        page.setStyleSheet(f"QWidget {{ background-color: black; }}")

        # Use absolute positioning for overlays
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Full-bleed video widget
        self.video_widget = QVideoWidget(page)
        self.video_widget.setMinimumHeight(480)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.video_widget, stretch=1)

        # Subtitle overlay (positioned at bottom, above transport bar)
        self.subtitle_label = ClickableSubtitleLabel(page, vocabulary_seen=self.analytics_vocabulary)
        self.subtitle_label.setFixedHeight(80)
        self.subtitle_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.subtitle_label.clicked.connect(self._on_subtitle_click)
        self.subtitle_label.background_clicked.connect(lambda _mods: self._clear_selection_state())
        self.subtitle_label.setStyleSheet("""
            ClickableSubtitleLabel {
                background-color: transparent;
            }
        """)
        layout.addWidget(self.subtitle_label, stretch=0)

        # Transport bar with full controls
        self.transport_bar = TransportBar()
        self.transport_bar.play_pause_clicked.connect(self._toggle_play_pause)
        self.transport_bar.replay_clicked.connect(self._replay_subtitle)
        self.transport_bar.slider_pressed.connect(self._on_slider_pressed)
        self.transport_bar.slider_released.connect(self._on_slider_released)
        self.transport_bar.slider_moved.connect(self._on_slider_moved)
        self.transport_bar.speed_changed.connect(self._on_speed_changed)
        self.transport_bar.volume_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self.transport_bar, stretch=0)

        # Keep references for backward compatibility
        self.play_pause_button = self.transport_bar.play_pause_button
        self.position_slider = self.transport_bar.position_slider
        self.time_label = self.transport_bar.time_label

        # Media player setup
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.media_player.errorOccurred.connect(self._on_media_error)
        self.media_player.mediaStatusChanged.connect(self._on_media_status_changed)

        return page


    def _set_status(self, message, timeout_ms=4000):
        """Update status message (legacy method)."""
        self.status_summary_label.setText(message)

    def _position_card_feedback_toast(self):
        if not hasattr(self, "card_feedback_toast"):
            return
        toast = self.card_feedback_toast
        margin = 20
        top = self.command_bar.height() + margin
        x = max(margin, self.width() - toast.width() - margin)
        toast.move(x, top)

    def _build_card_feedback_body(self, sentence: str, note_id=None, reason: str = ""):
        lines = [
            f"Target word: {self.selection.word}",
            f"Translation: {self.selection.translation}",
            f"Card text: {sentence}",
        ]
        if self.current_source_name:
            lines.append(f"Source: {self.current_source_name}")
        if self.current_source_location:
            lines.append(f"Location: {self.current_source_location}")
        if note_id is not None:
            lines.append(f"Note ID: {note_id}")
        if reason:
            lines.append(f"Reason: {reason}")
        return "\n".join(lines)

    def _show_card_feedback(self, title: str, sentence: str, variant: str, note_id=None, reason: str = ""):
        self._set_status(title)
        self.card_feedback_toast.show_message(
            title=title,
            body=self._build_card_feedback_body(sentence, note_id=note_id, reason=reason),
            variant=variant,
        )
        self._position_card_feedback_toast()

    def _open_data_folder(self):
        subprocess.Popen(["explorer", str(DATA_ROOT)])

    def _show_queue_dialog(self):
        entries = load_queue_entries()
        if self.queue_dialog is None:
            self.queue_dialog = QueueDialog(self)
            self.queue_dialog.process_button.clicked.connect(self._process_queue_from_dialog)
        self.queue_dialog.refresh(entries)
        self.queue_dialog.show()
        self.queue_dialog.raise_()
        self.queue_dialog.activateWindow()

    def _process_queue_from_dialog(self):
        self._process_queue()
        if self.queue_dialog:
            self.queue_dialog.refresh(load_queue_entries())

    def _refresh_queue_summary(self):
        count = queue_count()
        self.queue_summary_label.setText(
            f"Queued cards: {count}\nStructured queue: {QUEUE_JSON_PATH}\nProcessed log: {PROCESSED_LOG_PATH}"
        )

    def _check_internet_connection(self):
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return True
        except OSError:
            return False

    def _determine_translation_mode(self):
        logger.debug("Determining available translation mode")
        # Check availability without creating new instances unnecessarily
        if self._check_internet_connection():
            # Use cached online backend if available, otherwise create temporary one for check
            online_backend = self._online_backend if self._online_backend is not None else OnlineTranslationBackend()
            if online_backend.is_available():
                if self.translation_mode != "offline":
                    logger.info("Online translation backend available, using online mode")
                    self.translation_mode = "online"
                else:
                    logger.debug("Online backend available but staying in offline mode")
                self._update_translation_status_label()
                return

        # Fall back to offline mode if available
        logger.debug("Online backend unavailable, checking offline backend")
        offline_backend = self._offline_backend if self._offline_backend is not None else MarianMTTranslationBackend()
        if offline_backend.is_available():
            logger.info("Using offline translation mode")
            self.translation_mode = "offline"
        else:
            logger.warning("No translation backend available (online and offline both unavailable)")
        self._update_translation_status_label()

    def _update_translation_status_label(self):
        if self.translation_mode == "offline":
            self.translation_status_label.setText("Translation: Offline")
            self.mode_indicator_label.setText("Translation mode: OFFLINE")
        else:
            self.translation_status_label.setText("Translation: Online")
            self.mode_indicator_label.setText("Translation mode: ONLINE")

        # Update PDF status bar if it exists
        if hasattr(self, "pdf_status_bar"):
            self.pdf_status_bar.set_translation_mode(self.translation_mode)

        self.user_data["preferences"]["translation_mode"] = self.translation_mode
        save_user_data(self.user_data)

    def _toggle_translation_mode(self):
        logger.info(f"Toggling translation mode from {self.translation_mode}")
        if self.translation_mode == "online":
            # Check offline availability
            offline_backend = self._offline_backend if self._offline_backend is not None else MarianMTTranslationBackend()
            if not offline_backend.is_available():
                logger.warning("Cannot switch to offline mode: backend not available")
                self._set_status("Offline translation backend is not installed.")
                return
            logger.info("Switched to offline translation mode")
            self.translation_mode = "offline"
        else:
            # Check online availability
            online_backend = self._online_backend if self._online_backend is not None else OnlineTranslationBackend()
            if not online_backend.is_available():
                logger.warning("Cannot switch to online mode: backend not available")
                self._set_status("Online translation backend is not installed.")
                return
            logger.info("Switched to online translation mode")
            self.translation_mode = "online"
        self._update_translation_status_label()

    def _get_translation_language_codes(self):
        if self.translation_mode == "offline":
            return (
                get_marian_language_code(self.learning_language),
                get_marian_language_code(self.native_language),
            )
        return (
            get_google_language_code(self.learning_language),
            get_google_language_code(self.native_language),
        )

    def _set_learning_language(self, code):
        self.learning_language = normalize_language_code(code, DEFAULT_LEARNING_LANGUAGE)
        self._reset_translation_cache()
        self.user_data["preferences"]["learning_language"] = self.learning_language
        save_user_data(self.user_data)
        self._set_status(f"Learning language: {get_language_label(self.learning_language)}")

    def _set_native_language(self, code):
        self.native_language = normalize_language_code(code, DEFAULT_NATIVE_LANGUAGE)
        self._reset_translation_cache()
        self.user_data["preferences"]["native_language"] = self.native_language
        save_user_data(self.user_data)
        self._set_status(f"Native language: {get_language_label(self.native_language)}")

    def _reset_translation_cache(self):
        self.translation_cache.clear()
        self._translation_context_version += 1
        # Reset backend instances when cache is reset (language change)
        self._online_backend = None

        # Clear MarianMT model cache when language changes
        if self._offline_backend is not None:
            if hasattr(self._offline_backend, 'clear_model_cache'):
                self._offline_backend.clear_model_cache()
        self._offline_backend = None

    def _translation_cache_key(self, text):
        return (self.learning_language, self.native_language, text)

    def _get_translation_backend(self):
        """Get or create the appropriate translation backend, reusing instances."""
        if self.translation_mode == "online":
            if self._online_backend is None:
                self._online_backend = OnlineTranslationBackend()
            return self._online_backend
        else:
            if self._offline_backend is None:
                self._offline_backend = MarianMTTranslationBackend()
            return self._offline_backend

    def _start_translation_request(self, text, *, visible):
        if not text:
            return
        key = self._translation_cache_key(text)
        if key in self.translation_cache:
            if visible:
                logger.debug(f"Translation cache hit for text: {text[:50]}...")
                self._cache_hits += 1
                self.selection.translation = self.translation_cache[key]
                self._update_selection_panel()
                self._update_action_buttons()
            return

        existing_request_id = self._translation_requests_by_key.get(key)
        if existing_request_id is not None:
            logger.debug(f"Translation already in progress (request_id={existing_request_id})")
            if visible:
                self.current_request_id = existing_request_id
                request = self._translation_requests.get(existing_request_id)
                if request is not None:
                    request["visible"] = True
                self.selection.translation = "translating..."
                self._update_selection_panel()
                self._update_action_buttons()
            return existing_request_id

        self._next_translation_request_id += 1
        request_id = self._next_translation_request_id
        if visible:
            logger.debug(f"Translation cache miss, starting new request")
            self._cache_misses += 1
            self.current_request_id = request_id
            self.selection.translation = "translating..."
            self._update_selection_panel()
            self._update_action_buttons()
        backend = self._get_translation_backend()
        src_lang, dest_lang = self._get_translation_language_codes()
        logger.info(f"Starting translation request {request_id} (backend={self.translation_mode}, {src_lang}->{dest_lang}, visible={visible}): {text[:100]}...")
        task = TranslateTask(request_id, text, src_lang, dest_lang, backend)
        self._translation_requests[request_id] = {
            "key": key,
            "visible": visible,
            "context_version": self._translation_context_version,
        }
        self._translation_requests_by_key[key] = request_id
        task.signals.finished.connect(self._on_translation_done)
        task.signals.failed.connect(self._on_translation_failed)
        self.thread_pool.start(task)
        return request_id

    def _request_translation(self, text):
        self._start_translation_request(text, visible=True)

    def _prefetch_translations(self, texts):
        """
        Prefetch translations for multiple texts efficiently.
        Uses batch translation for online mode to minimize API calls.
        """
        if not texts:
            return

        # Filter out texts that are already cached or being requested
        texts_to_fetch = []
        for text in texts:
            if not text:
                continue
            key = self._translation_cache_key(text)
            # Skip if already cached or already being requested
            if key not in self.translation_cache and key not in self._translation_requests_by_key:
                texts_to_fetch.append(text)

        if not texts_to_fetch:
            return

        # For online mode, use batch translation for efficiency
        if self.translation_mode == "online":
            self._prefetch_translations_batch(texts_to_fetch)
        else:
            # For offline mode, process individually (batch not implemented yet)
            for text in texts_to_fetch:
                self._start_translation_request(text, visible=False)

    def _prefetch_translations_batch(self, texts):
        """
        Prefetch translations using batch API calls.
        Processes texts in batches of 50 to avoid overwhelming the API.
        """
        BATCH_SIZE = 50

        # Process in batches
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            backend = self._get_translation_backend()
            src_lang, dest_lang = self._get_translation_language_codes()

            # Create a batch translation task
            task = BatchTranslateTask(batch, src_lang, dest_lang, backend)
            task.signals.finished.connect(self._on_batch_translation_done)
            task.signals.failed.connect(self._on_batch_translation_failed)
            self.thread_pool.start(task)

    def _iter_unique_clean_words(self, values):
        seen = set()
        for value in values:
            cleaned = self._clean_word(value)
            if not cleaned:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            yield cleaned

    def _on_translation_done(self, request_id, source_text, translated_text):
        logger.info(f"Translation completed (request_id={request_id}): {source_text[:50]}... -> {translated_text[:50]}...")
        request = self._translation_requests.pop(request_id, None)
        if request is None:
            logger.debug(f"Translation request {request_id} not found (may have been cancelled)")
            return
        key = request["key"]
        if self._translation_requests_by_key.get(key) == request_id:
            self._translation_requests_by_key.pop(key, None)
        if request["context_version"] != self._translation_context_version:
            logger.debug(f"Translation request {request_id} context stale, discarding")
            return
        self.translation_cache[key] = translated_text
        logger.debug(f"Cached translation (cache size={len(self.translation_cache)})")
        if not request["visible"] or request_id != self.current_request_id:
            logger.debug(f"Translation request {request_id} not visible or not current, skipping UI update")
            return
        self.selection.translation = translated_text
        self._update_selection_panel()
        self._update_action_buttons()

    def _on_translation_failed(self, request_id, error_message):
        logger.error(f"Translation failed (request_id={request_id}): {error_message}")
        request = self._translation_requests.pop(request_id, None)
        if request is None:
            logger.debug(f"Translation request {request_id} not found")
            return
        key = request["key"]
        if self._translation_requests_by_key.get(key) == request_id:
            self._translation_requests_by_key.pop(key, None)
        if (
            request["context_version"] != self._translation_context_version
            or not request["visible"]
            or request_id != self.current_request_id
        ):
            logger.debug(f"Translation request {request_id} stale or not visible, skipping error display")
            return
        self.selection.translation = f"Translation error: {error_message}"
        self._update_selection_panel()
        self._update_action_buttons()
        self._set_status(f"Translation failed: {error_message}")

    def _on_batch_translation_done(self, texts, translations):
        """Handle completion of batch translation for prefetching."""
        if len(texts) != len(translations):
            logger.error(f"Batch translation count mismatch: {len(texts)} texts vs {len(translations)} translations")
            return

        # Cache all the translations
        for text, translation in zip(texts, translations):
            key = self._translation_cache_key(text)
            self.translation_cache[key] = translation

        # Determine location based on mode
        if self.mode_manager.current_mode == WorkspaceMode.PDF:
            location_info = f"page {self.current_page_index + 1}"
        elif self.mode_manager.current_mode == WorkspaceMode.VIDEO:
            if hasattr(self, 'current_subtitle') and self.current_subtitle:
                location_info = f"line {self.current_subtitle.index}"
            else:
                location_info = "line ?"
        else:
            location_info = "unknown location"

        # Create word sample (first 5 words)
        sample_size = min(5, len(texts))
        word_sample = ", ".join(texts[:sample_size])

        logger.info(f"Batch translation completed: {len(texts)} words on {location_info}: {word_sample}")

    def _on_batch_translation_failed(self, error_message):
        """Handle batch translation failure - log but don't show to user since it's background."""
        logger.warning(f"Batch translation prefetch failed: {error_message}")

    def _translate_word_field_input(self):
        text = self.word_value.text().strip()
        if not text:
            self.selection.word = ""
            self.selection.translation = ""
            self._update_selection_panel()
            self._update_action_buttons()
            return
        self.selection.word = text
        self._request_translation(text)

    def _update_selection_panel(self):
        """Update legacy selection panel and show translation popover."""
        # Update legacy widgets (for backward compatibility)
        if self.word_value.text() != self.selection.word:
            self.word_value.setText(self.selection.word)
        self.sentence_value.setText(self.selection.sentence)
        self.translation_value.setText(self.selection.translation)
        if self.current_source_name:
            self.source_header_label.setText(
                f"{self.current_source_name} | {self.current_source_location or 'location unavailable'}"
            )
        else:
            self.source_header_label.setText("Nothing selected")

        should_show_overlay = bool(
            self.selection.word
            and self.selection.translation
            and not self.selection.translation.startswith("Translation error:")
        )
        if should_show_overlay:
            self._show_translation_popover()
        else:
            self._close_popover()

    def _update_action_buttons(self):
        has_selection = bool(self.selection.word)
        has_translation = bool(
            self.selection.translation
            and self.selection.translation != "translating..."
            and not self.selection.translation.startswith("Translation error:")
        )
        self.add_now_button.setEnabled(has_selection and has_translation)
        self.add_queue_button.setEnabled(has_selection and has_translation)

    def _clear_selection_state(self):
        had_pdf_selection = not self.selection.pdf.is_empty()

        self.selection.clear_all()

        if hasattr(self, "subtitle_label"):
            self.subtitle_label.highlight_word_range(None, None)

        if had_pdf_selection and self.doc and self.mode_manager.current_mode == WorkspaceMode.PDF:
            self._render_current_page()

        self._update_selection_panel()
        self._update_action_buttons()
        self._close_popover()

    def _show_translation_popover(self):
        """Show the inline translation overlay above the selected span."""
        if not self.selection.translation or self.selection.translation.startswith("Translation error:"):
            return

        self.translation_popover.set_content(
            word=self.selection.word,
            meaning=self.selection.translation,
            sentence=self.selection.sentence,
            sentence_translation="",
            metadata="",
        )

        anchor_rect = self._current_selection_anchor_rect()
        if anchor_rect.isNull():
            self._close_popover()
            return

        # Convert anchor rect from main window coordinates to global screen coordinates
        anchor_rect_global = QRect(
            self.mapToGlobal(anchor_rect.topLeft()),
            anchor_rect.size()
        )

        self.translation_popover.set_anchor_rect(anchor_rect_global)
        self.translation_popover.position_near_word(anchor_rect_global)
        self.translation_popover.show_animated()

    def _on_popover_edit_requested(self):
        """Handle edit request from popover."""
        # TODO: Implement edit flow - expand popover or show edit dialog
        pass

    def _on_popover_closed(self):
        """Handle popover close event."""
        pass

    def _close_popover(self):
        """Close the translation popover if visible."""
        if self.translation_popover.isVisible():
            self.translation_popover.close()

    def _current_selection_anchor_rect(self):
        if self.mode_manager.current_mode == WorkspaceMode.VIDEO:
            return self._subtitle_selection_anchor_rect()
        if self.mode_manager.current_mode == WorkspaceMode.PDF:
            return self._pdf_selection_anchor_rect()
        return QRect()

    def _subtitle_selection_anchor_rect(self):
        if not self.selection.video.selected_indices:
            return QRect()

        local_rect = self.subtitle_label.selection_anchor_rect(
            self.selection.video.selected_indices[0],
            self.selection.video.selected_indices[-1],
        )
        if local_rect.isNull():
            return QRect()

        top_left = self.subtitle_label.mapTo(self, local_rect.topLeft())
        return QRect(top_left, local_rect.size())

    def _pdf_selection_anchor_rect(self):
        if not self.selection.pdf.selected_words:
            return QRect()

        first_line_key = (int(self.selection.pdf.selected_words[0][5]), int(self.selection.pdf.selected_words[0][6]))
        first_line_words = [word for word in self.selection.pdf.selected_words if (int(word[5]), int(word[6])) == first_line_key]
        if not first_line_words:
            return QRect()

        left = min(word[0] for word in first_line_words)
        top = min(word[1] for word in first_line_words)
        right = max(word[2] for word in first_line_words)
        bottom = max(word[3] for word in first_line_words)

        local_rect = QRect(
            int(left * self.zoom_factor),
            int(top * self.zoom_factor),
            max(1, int((right - left) * self.zoom_factor)),
            max(1, int((bottom - top) * self.zoom_factor)),
        )
        top_left = self.pdf_label.mapTo(self, local_rect.topLeft())
        return QRect(top_left, local_rect.size())

    def _update_command_bar_stats(self):
        """Update the stats chip in the command bar."""
        total_count = len(self.analytics_vocabulary)
        # TODO: Calculate today_count when we add timestamps to vocabulary
        today_count = 0
        self.command_bar.set_stats(today_count, total_count)

    def _jump_to_page(self, page_number: int):
        if not self.doc or not (1 <= page_number <= self.doc.page_count):
            return
        self.current_page_index = page_number - 1
        self.selection.pdf.highlight_bboxes = []
        self._clear_selection_state()
        self._render_current_page()
        self._persist_session()

    def _replay_subtitle(self):
        """Jump to the start of the current subtitle."""
        if self.current_subtitle:
            self.media_player.setPosition(self.current_subtitle.start_ms)

    def _on_speed_changed(self, speed: float):
        """Handle playback speed change."""
        if self.media_player:
            self.media_player.setPlaybackRate(speed)

    def _on_volume_changed(self, value: int):
        """Handle volume change (0-100)."""
        if self.audio_output:
            self.audio_output.setVolume(value / 100.0)

    def _clean_word(self, value):
        start = 0
        end = len(value)
        while start < end and not (value[start].isalpha() or value[start].isdigit() or value[start] == "_"):
            start += 1
        while end > start and not (value[end - 1].isalpha() or value[end - 1].isdigit() or value[end - 1] == "_"):
            end -= 1
        return value[start:end].strip()

    def _refresh_anki_status(self):
        self.anki_check_request_id += 1
        request_id = self.anki_check_request_id
        logger.info(f"Checking Anki connection status (request_id={request_id})")
        self.anki_status_label.setText("Anki: checking...")
        task = AnkiStatusTask(request_id)
        task.signals.finished.connect(self._on_anki_status_checked)
        self.thread_pool.start(task)

    def _on_anki_status_checked(self, request_id, connected, words):
        if request_id != self.anki_check_request_id:
            logger.debug(f"Anki status check stale (request_id={request_id}, current={self.anki_check_request_id}), ignoring")
            return
        vocab_count = len(words) if words is not None else 0
        logger.info(f"Anki status checked (request_id={request_id}): connected={connected}, vocabulary_count={vocab_count}")
        self.is_anki_connected = connected
        self.anki_status_label.setText("Anki: connected" if connected else "Anki: not connected")
        self.health_label.setText(
            f"Anki: {'ready' if connected else 'not connected'}\nTranslation backend: {self.translation_mode}"
        )
        if words is not None:
            save_snapshot(words)
            self.analytics_vocabulary.update(words)
            logger.debug(f"Updated analytics vocabulary: {len(self.analytics_vocabulary)} words total")
            self._refresh_word_highlights()

    def _refresh_word_highlights(self):
        if self.doc and self.current_pdf_path:
            self._render_current_page()
        if hasattr(self, "subtitle_label"):
            self.subtitle_label.set_vocabulary_seen(self.analytics_vocabulary)

    def _start_anki(self):
        if not os.path.exists(ANKI_PATH):
            logger.warning(f"Anki executable not found at {ANKI_PATH}")
            QMessageBox.warning(self, "Anki Not Found", f"Anki executable not found at:\n{ANKI_PATH}")
            return
        try:
            logger.info(f"Starting Anki process: {ANKI_PATH}")
            self.anki_process = subprocess.Popen([ANKI_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Anki process started successfully (PID: {self.anki_process.pid})")
        except Exception as exc:
            logger.error(f"Failed to start Anki: {exc}", exc_info=True)
            QMessageBox.critical(self, "Start Anki Failed", str(exc))
            return
        self._set_status("Anki started. Checking connection...")
        QTimer.singleShot(3500, self._refresh_anki_status)

    def _build_note_sentence(self):
        sentence = self.selection.sentence or self.selection.word
        if sentence in self.sentence_counts:
            self.sentence_counts[sentence] += 1
            return f"{sentence} ({self.sentence_counts[sentence]})"
        self.sentence_counts[sentence] = 1
        return sentence

    def _record_successful_card_add(self, word_text):
        analytics = self.user_data["analytics"]
        old_total = int(analytics.get("cards_added_total") or 0)
        analytics["cards_added_total"] = old_total + 1
        self.analytics_vocabulary.update(token.lower() for token in re.findall(r"\b\w+\b", word_text, flags=re.UNICODE))
        analytics["vocabulary_seen"] = sorted(self.analytics_vocabulary)
        logger.info(f"Recorded card add for '{word_text}' (total cards: {analytics['cards_added_total']}, vocabulary: {len(self.analytics_vocabulary)} words)")
        save_user_data(self.user_data)

        # Update UI to reflect new vocabulary state
        self.subtitle_label.set_vocabulary_seen(self.analytics_vocabulary)
        self._update_command_bar_stats()

        # Re-render PDF to update word highlighting
        if self.doc and self.mode_manager.current_mode == WorkspaceMode.PDF:
            logger.debug("Re-rendering PDF to update word highlighting")
            self._render_current_page()

    def _queue_payload(self):
        return {
            "sentence": self.selection.sentence or self.selection.word,
            "word": self.selection.word,
            "translation": self.selection.translation,
            "source_name": self.current_source_name,
            "source_type": self.mode_manager.mode_string(),
            "location": self.current_source_location,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "status": "queued",
        }

    def _queue_current_selection_for_later(self, reason: str):
        payload = self._queue_payload()
        logger.info(f"Queueing card for later (reason: {reason}): word='{payload['word']}', sentence='{payload['sentence'][:50]}...'")
        append_queue_entry(payload)
        self._refresh_queue_summary()
        self._show_card_feedback("Queued for later", payload["sentence"], "queued", reason=reason)

    def _add_now(self):
        if not self.selection.word or not self.selection.translation:
            logger.debug("Skipping card add: no word or translation selected")
            return
        logger.info(f"Adding card now: word='{self.selection.word}', translation='{self.selection.translation}', anki_connected={self.is_anki_connected}")
        if not self.is_anki_connected:
            logger.warning("Anki not connected, queueing card instead")
            try:
                self._queue_current_selection_for_later("AnkiConnect is not available")
            except Exception as exc:
                logger.error(f"Failed to queue card: {exc}", exc_info=True)
                QMessageBox.critical(self, "Queue Write Failed", str(exc))
            return
        try:
            note_sentence = self._build_note_sentence()
            note_id = add_anki_card(note_sentence, self.selection.word, self.selection.translation)
            logger.info(f"Successfully added card to Anki (note_id={note_id}): '{note_sentence}'")
            self._record_successful_card_add(self.selection.word)
            self._show_card_feedback("Added to Anki", note_sentence, "added", note_id=note_id)
            self._close_popover()
        except Exception as exc:
            if isinstance(exc, ConnectionError):
                logger.error(f"Anki connection error during card add: {exc}", exc_info=True)
                try:
                    self._queue_current_selection_for_later(str(exc))
                except Exception as queue_exc:
                    logger.error(f"Failed to queue card after connection error: {queue_exc}", exc_info=True)
                    QMessageBox.critical(self, "Queue Write Failed", str(queue_exc))
                return
            logger.error(f"Failed to add card to Anki: {exc}", exc_info=True)
            QMessageBox.critical(self, "Anki Add Failed", str(exc))

    def _add_to_queue(self):
        if not self.selection.word or not self.selection.translation:
            logger.debug("Skipping queue add: no word or translation selected")
            return
        try:
            payload = self._queue_payload()
            logger.info(f"Adding to queue: word='{payload['word']}', sentence='{payload['sentence'][:50]}...'")
            append_queue_entry(payload)
            self._refresh_queue_summary()
            self._show_card_feedback("Saved to queue", payload["sentence"], "queued")
        except Exception as exc:
            logger.error(f"Failed to add card to queue: {exc}", exc_info=True)
            QMessageBox.critical(self, "Queue Write Failed", str(exc))

    def _process_queue(self):
        entries = load_queue_entries()
        queue_size = len(entries)
        logger.info(f"Processing queue with {queue_size} entries")
        if not entries:
            logger.debug("Queue is empty")
            QMessageBox.information(self, "Queue Empty", "No queued cards found.")
            return
        if not self.is_anki_connected:
            logger.warning("Cannot process queue: Anki not connected")
            QMessageBox.warning(self, "Anki Not Connected", "AnkiConnect is not available.")
            return

        successful_entries = []
        failed_entries = []
        for i, entry in enumerate(entries, 1):
            logger.debug(f"Processing queue entry {i}/{queue_size}: word='{entry.get('word')}'")
            sentence = entry["sentence"]
            if sentence in self.sentence_counts:
                self.sentence_counts[sentence] += 1
                sentence_for_note = f"{sentence} ({self.sentence_counts[sentence]})"
            else:
                self.sentence_counts[sentence] = 1
                sentence_for_note = sentence
            try:
                add_anki_card(sentence_for_note, entry["word"], entry["translation"])
                successful_entries.append(entry)
                self._record_successful_card_add(entry["word"])
            except Exception as exc:
                logger.error(f"Failed to add queued card '{entry.get('word')}': {exc}", exc_info=True)
                failed_entries.append(entry)

        if successful_entries:
            append_processed_log(successful_entries)
        save_queue_entries(failed_entries)
        self._refresh_queue_summary()
        logger.info(f"Queue processing complete: {len(successful_entries)} added, {len(failed_entries)} failed")
        QMessageBox.information(
            self,
            "Queue Processed",
            f"Added: {len(successful_entries)}\nFailed: {len(failed_entries)}\nLog: {PROCESSED_LOG_PATH}",
        )

    def _open_content_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open source", "", self.SUPPORTED_CONTENT_FILTER)
        if not path:
            return
        if Path(path).suffix.lower() == ".pdf":
            self._load_pdf(path)
        else:
            self._load_video(path)

    def _close_current_file(self):
        if self.media_player:
            self.media_player.stop()
        if self.doc:
            self.doc.close()
            self.doc = None
        self.current_pdf_path = ""
        self.current_video_path = ""
        self.current_srt_path = ""
        self.subtitle_parser = None
        self.current_source_name = ""
        self._clear_selection_state()
        self.command_bar.set_title("No document loaded")
        self.command_bar.set_file_loaded(False)
        self.command_bar.set_page_info(0, 0)
        self._persist_session()

        # Update mode manager
        self.mode_manager.set_pdf_loaded(False)
        self.mode_manager.set_video_loaded(False)
        self.mode_manager.set_mode(WorkspaceMode.WELCOME, force=True)

    def _load_pdf(self, path, initial_page_index=0):
        logger.info(f"Loading PDF: {path}")
        try:
            self.doc = fitz.open(path)
            logger.info(f"PDF opened successfully: {Path(path).name} ({self.doc.page_count} pages)")
        except Exception as exc:
            logger.error(f"Failed to open PDF '{path}': {exc}", exc_info=True)
            QMessageBox.critical(self, "PDF Error", f"Failed to open PDF:\n{exc}")
            return

        self.current_pdf_path = path
        self.current_page_index = max(0, min(initial_page_index, self.doc.page_count - 1))
        self.current_source_name = Path(path).name
        self.current_source_location = f"Page {self.current_page_index + 1}"
        logger.debug(f"PDF page set to {self.current_page_index + 1}/{self.doc.page_count}")
        self._clear_selection_state()
        QTimer.singleShot(0, self._fit_width)
        self._update_source_summary()
        self._persist_session()
        self._set_status(f"Opened PDF: {Path(path).name}")

        # Update command bar
        self.command_bar.set_title(
            Path(path).name,
            f"{self.doc.page_count} pages"
        )
        self.command_bar.set_file_loaded(True)
        self.command_bar.set_page_info(self.current_page_index + 1, self.doc.page_count)
        self._update_command_bar_stats()

        # Update mode manager
        self.mode_manager.set_pdf_loaded(True)
        self.mode_manager.set_mode(WorkspaceMode.PDF, force=True)

        # Add to recent files
        from immersion_app.core.recent_files import add_recent_file
        add_recent_file(
            self.user_data,
            str(self.current_pdf_path),
            "pdf",
            {"page_index": self.current_page_index}
        )
        save_user_data(self.user_data)

    def _render_current_page(self):
        if not self.doc:
            return

        page = self.doc.load_page(self.current_page_index)
        matrix = fitz.Matrix(self.zoom_factor, self.zoom_factor)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()

        # Get words before painting
        self.page_words = page.get_text("words")
        self.page_word_order = sorted(
            self.page_words,
            key=lambda w: (int(w[5]), int(w[6]), int(w[7]), float(w[1]), float(w[0])),
        )

        # Draw word highlights
        painter = QPainter(image)

        # 1. Draw seen/new state highlights for all words
        for word_obj in self.page_words:
            x0, y0, x1, y1, text = word_obj[0:5]

            # Clean the word text for vocabulary lookup
            cleaned_text = self._clean_word(text)
            if not cleaned_text:
                continue

            # Check if word is in vocabulary (seen state)
            is_seen = cleaned_text.lower() in self.analytics_vocabulary

            # Choose color based on state
            if is_seen:
                color = Theme.to_qcolor(Theme.HL_SEEN)
            else:
                color = Theme.to_qcolor(Theme.HL_NEW)

            # Draw background rectangle
            rect_x = int(x0 * self.zoom_factor)
            rect_y = int(y0 * self.zoom_factor)
            rect_w = max(1, int((x1 - x0) * self.zoom_factor))
            rect_h = max(1, int((y1 - y0) * self.zoom_factor))

            painter.fillRect(rect_x, rect_y, rect_w, rect_h, color)

        # 2. Draw selection highlight on top (for currently selected word)
        if self.selection.pdf.highlight_bboxes:
            selection_color = Theme.to_qcolor(Theme.HL_SELECTED)
            for x0, y0, x1, y1 in self.selection.pdf.highlight_bboxes:
                rect_x = int(x0 * self.zoom_factor)
                rect_y = int(y0 * self.zoom_factor)
                rect_w = max(1, int((x1 - x0) * self.zoom_factor))
                rect_h = max(1, int((y1 - y0) * self.zoom_factor))
                painter.fillRect(rect_x, rect_y, rect_w, rect_h, selection_color)

        painter.end()

        pixmap = QPixmap.fromImage(image)
        self.pdf_label.setPixmap(pixmap)
        self.pdf_label.resize(pixmap.size())

        self.page_word_index = {self._word_key(word): idx for idx, word in enumerate(self.page_word_order)}
        self.page_line_words = self._build_line_index(self.page_words)
        self._prefetch_translations(self._iter_unique_clean_words(word[4] for word in self.page_word_order))
        self.current_source_location = f"Page {self.current_page_index + 1}"
        self._update_source_summary()
        self.command_bar.set_page_info(self.current_page_index + 1, self.doc.page_count)

        # Update zoom display in status bar
        self.pdf_status_bar.set_zoom_level(self.zoom_factor)
        if (
            self.mode_manager.current_mode == WorkspaceMode.PDF
            and self.selection.pdf.selected_words
            and self.selection.translation
            and self.selection.translation != "translating..."
            and not self.selection.translation.startswith("Translation error:")
        ):
            self._show_translation_popover()

    def _build_line_index(self, words):
        line_map = {}
        for word in words:
            key = (int(word[5]), int(word[6]))
            line_map.setdefault(key, []).append(word)
        for key in line_map:
            line_map[key].sort(key=lambda item: item[0])
        return line_map

    def _word_key(self, word):
        return (
            float(word[0]),
            float(word[1]),
            float(word[2]),
            float(word[3]),
            str(word[4]),
            int(word[5]),
            int(word[6]),
            int(word[7]),
        )

    def _on_pdf_click(self, point, modifiers):
        if not self.doc or not self.page_words:
            return
        x_pdf = point.x() / self.zoom_factor
        y_pdf = point.y() / self.zoom_factor
        hit_word = None
        for word in self.page_word_order:
            if word[0] <= x_pdf <= word[2] and word[1] <= y_pdf <= word[3]:
                hit_word = word
                break
        if not hit_word:
            self._clear_selection_state()
            return

        shift_pressed = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        selected_words = self._resolve_selected_words(hit_word, shift_pressed)
        cleaned_words = [self._clean_word(selected[4]) for selected in selected_words if self._clean_word(selected[4])]
        if not cleaned_words:
            return
        self.selection.pdf.highlight_bboxes = [(w[0], w[1], w[2], w[3]) for w in selected_words]
        self.selection.pdf.selected_words = list(selected_words)
        self.selection.video.selected_indices = []
        self.selection.word = " ".join(cleaned_words)
        self.selection.sentence = self._extract_context_for_selection(selected_words)
        self.current_source_location = f"Page {self.current_page_index + 1}"
        self._update_selection_panel()
        self._update_action_buttons()
        self._render_current_page()
        self._request_translation(self.selection.word)

    def _resolve_selected_words(self, hit_word, shift_pressed):
        hit_key = self._word_key(hit_word)
        if not shift_pressed or self.selection.pdf.anchor_key is None:
            self.selection.pdf.anchor_key = hit_key
            return [hit_word]
        anchor_index = self.page_word_index.get(self.selection.pdf.anchor_key)
        hit_index = self.page_word_index.get(hit_key)
        if anchor_index is None or hit_index is None:
            self.selection.pdf.anchor_key = hit_key
            return [hit_word]
        start_idx = min(anchor_index, hit_index)
        end_idx = max(anchor_index, hit_index)
        return self.page_word_order[start_idx : end_idx + 1]

    def _extract_context_for_selection(self, selected_words):
        if not selected_words:
            return ""
        line_key = (int(selected_words[0][5]), int(selected_words[0][6]))
        line_words = self.page_line_words.get(line_key, [selected_words[0]])
        return " ".join(item[4] for item in line_words)

    def _prev_page(self):
        if not self.doc or self.current_page_index <= 0:
            return
        self.current_page_index -= 1
        self.selection.pdf.highlight_bboxes = []
        self._clear_selection_state()
        self._render_current_page()
        self._persist_session()

    def _next_page(self):
        if not self.doc or self.current_page_index >= self.doc.page_count - 1:
            return
        self.current_page_index += 1
        self.selection.pdf.highlight_bboxes = []
        self._clear_selection_state()
        self._render_current_page()
        self._persist_session()

    def _zoom_in(self):
        if self.doc:
            self.zoom_factor = min(4.0, self.zoom_factor + 0.25)
            self._render_current_page()

    def _zoom_out(self):
        if self.doc:
            self.zoom_factor = max(0.5, self.zoom_factor - 0.25)
            self._render_current_page()

    def _reset_zoom(self):
        """Reset zoom to 100% (factor 2.0)."""
        if self.doc:
            self.zoom_factor = 2.0
            self._render_current_page()

    def _fit_width(self):
        """Fit PDF to reading column width."""
        if not self.doc:
            return
        page = self.doc.load_page(self.current_page_index)
        # Get reading column widget (parent of scroll_area)
        reading_column = self.scroll_area.parent()
        # Account for margins (36px on each side = 72px total)
        available = max(200, reading_column.width() - 72)
        self.zoom_factor = max(0.5, min(4.0, available / page.rect.width))
        self._render_current_page()



    def _open_subtitle_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load subtitles", "", "SRT Files (*.srt)")
        if not path:
            return
        self._load_subtitles(path)

    def _load_video(self, path, restore_position_ms=0):
        """Load video with validation and error handling."""
        logger.info(f"Loading video: {path} (restore_position={restore_position_ms}ms)")

        # Validate file exists
        video_path = Path(path)
        if not video_path.exists():
            logger.error(f"Video file not found: {path}")
            QMessageBox.critical(self, "File Not Found", f"Video file does not exist:\n{path}")
            return

        # Validate file size (detect empty/corrupt files)
        file_size = video_path.stat().st_size
        logger.debug(f"Video file size: {file_size} bytes")
        if file_size < 1024:  # Less than 1KB
            logger.warning(f"Video file too small ({file_size} bytes), may be corrupted: {path}")
            QMessageBox.warning(
                self,
                "Invalid File",
                f"Video file appears to be empty or corrupted:\n{video_path.name}"
            )
            return

        # Continue with existing loading logic...
        self.current_video_path = path
        self.current_source_name = Path(path).name
        self.current_source_location = "00:00"
        self.media_player.setSource(QUrl.fromLocalFile(path))
        if restore_position_ms > 0:
            logger.debug(f"Scheduling position restoration to {restore_position_ms}ms")
            QTimer.singleShot(400, lambda: self.media_player.setPosition(restore_position_ms))

        auto_srt = find_best_srt_for_video(path)
        if auto_srt:
            logger.info(f"Auto-detected subtitle file: {auto_srt}")
            self._load_subtitles(auto_srt)
        else:
            logger.debug("No subtitle file auto-detected")
            self.subtitle_parser = None
            self.current_srt_path = ""
            self.subtitle_label.set_subtitle(None)
        self._update_source_summary()
        self._persist_session()
        # Note: Don't set "Loaded video" status immediately - wait for mediaStatusChanged

        # Update command bar
        self.command_bar.set_title(
            Path(path).name,
            "Video"
        )
        self.command_bar.set_file_loaded(True)
        self._update_command_bar_stats()

        # Update mode manager
        self.mode_manager.set_video_loaded(True)
        self.mode_manager.set_mode(WorkspaceMode.VIDEO, force=True)

        # Add to recent files
        from immersion_app.core.recent_files import add_recent_file
        position_ms = self.media_player.position() if self.media_player else 0
        add_recent_file(
            self.user_data,
            str(self.current_video_path),
            "video",
            {"video_position_ms": position_ms}
        )
        save_user_data(self.user_data)

    def _load_subtitles(self, srt_path):
        logger.info(f"Loading subtitles: {srt_path}")
        try:
            self.subtitle_parser = SRTParser.from_file(srt_path)
            entry_count = len(self.subtitle_parser.entries) if self.subtitle_parser else 0
            logger.info(f"Loaded {entry_count} subtitle entries from {Path(srt_path).name}")
            self.current_srt_path = srt_path
            self._persist_session()
            self._set_status(f"Loaded subtitles: {Path(srt_path).name}")
        except Exception as exc:
            logger.error(f"Failed to load subtitles from {srt_path}: {exc}", exc_info=True)
            QMessageBox.critical(self, "Subtitle Error", f"Failed to parse subtitles:\n{exc}")

    def _generate_subtitles_interactive(self):
        if not self.current_video_path:
            QMessageBox.information(self, "No Video", "Open a video source first.")
            return
        dialog = SubtitleGeneratorDialog(self, default_language=get_whisper_language_code(self.learning_language))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dialog.status_label.setText("Starting generation...")
        dialog.progress_bar.setVisible(True)
        worker = SubtitleGeneratorWorker(
            self.current_video_path,
            dialog.selected_model(),
            dialog.selected_language(),
        )
        worker.signals.progress.connect(dialog.status_label.setText)
        worker.signals.finished.connect(lambda srt_path: self._on_subtitle_generation_finished(dialog, srt_path))
        worker.signals.failed.connect(lambda message: QMessageBox.critical(self, "Subtitle Generation Error", message))
        self._subtitle_thread_pool.start(worker)

    def _on_subtitle_generation_finished(self, dialog, srt_path):
        dialog.status_label.setText("Finished")
        self._load_subtitles(srt_path)
        self._set_status(f"Generated subtitles: {Path(srt_path).name}")

    def _on_subtitle_click(self, word, token_index, modifiers):
        if not self.current_subtitle:
            return
        words = self.current_subtitle.words
        shift_pressed = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        selected_indices = self._resolve_selected_subtitle_indices(token_index, shift_pressed, len(words))
        cleaned_words = [self._clean_word(words[idx].word) for idx in selected_indices if self._clean_word(words[idx].word)]
        if not cleaned_words:
            return
        self.selection.word = " ".join(cleaned_words)
        self.selection.sentence = self.current_subtitle.text
        self.selection.video.selected_indices = list(selected_indices)
        self.selection.pdf.selected_words = []
        self.current_source_location = self._fmt_ms(self.media_player.position())
        self.subtitle_label.highlight_word_range(selected_indices[0], selected_indices[-1])
        self._update_selection_panel()
        self._update_action_buttons()
        self._request_translation(self.selection.word)

    def _resolve_selected_subtitle_indices(self, token_index, shift_pressed, token_count):
        subtitle_index = self.current_subtitle.index if self.current_subtitle else -1
        if (
            not shift_pressed
            or self.selection.video.anchor is None
            or self.selection.video.anchor[0] != subtitle_index
        ):
            self.selection.video.anchor = (subtitle_index, token_index)
            return [token_index]
        anchor_index = max(0, min(self.selection.video.anchor[1], token_count - 1))
        start = min(anchor_index, token_index)
        end = max(anchor_index, token_index)
        return list(range(start, end + 1))

    def _on_position_changed(self, position):
        if not self._is_slider_dragging:
            self.transport_bar.set_position(position)
        duration = self.media_player.duration()
        self.transport_bar.set_time(position, duration)
        self.current_source_location = self._fmt_ms(position)
        self.subtitle_offset_label.setText(f"Subtitle Offset: {self.subtitle_offset_ms / 1000.0:+.2f}s")
        self._refresh_subtitle_for_position(position)
        self._update_source_summary()

    def _refresh_subtitle_for_position(self, position):
        if not self.subtitle_parser:
            self.current_subtitle = None
            self.selection.video.anchor = None
            self.selection.video.selected_indices = []
            self.subtitle_label.set_subtitle(None)
            self._close_popover()
            return
        lookup_position = max(0, position - self.subtitle_offset_ms)
        subtitle = self.subtitle_parser.get_subtitle_at_time(lookup_position)
        if subtitle is None:
            self.current_subtitle = None
            self.selection.video.anchor = None
            self.selection.video.selected_indices = []
            self.subtitle_label.set_subtitle(None)
            self._close_popover()
            return
        if self.current_subtitle is None or subtitle.index != self.current_subtitle.index:
            self.current_subtitle = subtitle
            self.selection.video.anchor = None
            self.selection.video.selected_indices = []
            self.subtitle_label.set_subtitle(subtitle)
            self._prefetch_translations(self._iter_unique_clean_words(word.word for word in subtitle.words))
            self._close_popover()

    def _on_duration_changed(self, duration):
        self.transport_bar.set_duration(max(0, duration))
        self.transport_bar.set_time(0, duration)

    def _on_playback_state_changed(self, state):
        is_playing = self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.transport_bar.set_play_state(is_playing)

    def _toggle_play_pause(self):
        if self.workspace_stack.currentWidget() != self.video_page:
            return
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
        self.subtitle_offset_label.setText(f"Subtitle Offset: {self.subtitle_offset_ms / 1000.0:+.2f}s")
        self._refresh_subtitle_for_position(self.media_player.position())
        self._persist_session()

    def _on_slider_pressed(self):
        self._is_slider_dragging = True

    def _on_slider_released(self):
        self._is_slider_dragging = False
        self.media_player.setPosition(self.position_slider.value())

    def _on_slider_moved(self, value):
        self.time_label.setText(f"{self._fmt_ms(value)} / {self._fmt_ms(self.media_player.duration())}")

    def _on_media_error(self, error, error_string):
        """Handle QMediaPlayer errors with user-friendly messages."""
        from PySide6.QtMultimedia import QMediaPlayer

        if error == QMediaPlayer.Error.NoError:
            return

        # Log technical details
        logger.error(f"Media player error: {error}, error_string='{error_string}', file='{self.current_video_path}'")

        # Map to user-friendly messages
        error_messages = {
            QMediaPlayer.Error.ResourceError: "Could not access the video file. Check the file path and permissions.",
            QMediaPlayer.Error.FormatError: "Video format or codec not supported. Try converting to H.264/MP4.",
            QMediaPlayer.Error.NetworkError: "Network error occurred while loading the video.",
            QMediaPlayer.Error.AccessDeniedError: "Permission denied. Cannot access this video file.",
            QMediaPlayer.Error.ServiceMissingError: "Media playback service unavailable.",
        }

        user_message = error_messages.get(error, "Unknown video playback error")
        file_name = Path(self.current_video_path).name if self.current_video_path else "Unknown"

        detailed_message = f"{user_message}\n\nFile: {file_name}"

        if error == QMediaPlayer.Error.FormatError:
            detailed_message += "\n\nThis may be due to an unsupported codec (e.g., AV1)."
            detailed_message += "\nRecommended: Convert to H.264 codec with MP4 container."

        QMessageBox.critical(self, "Video Playback Error", detailed_message)
        self._set_status(f"Failed to load video: {user_message}")

    def _on_media_status_changed(self, status):
        """Monitor media loading status and detect issues early."""
        from PySide6.QtMultimedia import QMediaPlayer

        logger.debug(f"Media status changed: {status}")

        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            file_name = Path(self.current_video_path).name if self.current_video_path else "Unknown"
            logger.error(f"Invalid media detected: {self.current_video_path}")
            QMessageBox.warning(
                self,
                "Invalid Video",
                f"The video file could not be loaded: {file_name}\n\n"
                "This may be due to:\n"
                "• Unsupported codec (e.g., AV1)\n"
                "• Corrupted file\n"
                "• Incomplete download\n\n"
                "Try converting to H.264/MP4 format."
            )
            self._set_status("Invalid video file")
        elif status == QMediaPlayer.MediaStatus.LoadedMedia:
            self._set_status(f"Video ready: {Path(self.current_video_path).name}")

    def _fmt_ms(self, ms):
        total_sec = max(0, int(ms // 1000))
        m, s = divmod(total_sec, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"

    def _update_source_summary(self):
        if not self.current_source_name:
            self.source_summary_label.setText("No source loaded")
            return
        subtitle_state = Path(self.current_srt_path).name if self.current_srt_path else "No subtitles"
        self.source_summary_label.setText(
            f"Source: {self.current_source_name}\n"
            f"Type: {self.mode_manager.mode_string() or 'none'}\n"
            f"Location: {self.current_source_location or 'n/a'}\n"
            f"Subtitles: {subtitle_state}"
        )

    def _persist_session(self):
        session = self.user_data["last_session"]
        mode_string = self.mode_manager.mode_string()
        video_pos = int(self.media_player.position() if self.media_player else 0)

        session.update(
            {
                "content_type": mode_string,
                "pdf_path": self.current_pdf_path,
                "page_index": int(self.current_page_index),
                "video_path": self.current_video_path,
                "video_position_ms": video_pos,
                "srt_path": self.current_srt_path,
                "subtitle_offset_ms": int(self.subtitle_offset_ms),
            }
        )

        logger.debug(f"Persisting session: mode={mode_string}, pdf={self.current_pdf_path or 'none'}, page={self.current_page_index}, video={self.current_video_path or 'none'}, position={video_pos}ms")

        # Update workspace view based on mode
        mode = self.mode_manager.current_mode
        if mode == WorkspaceMode.VIDEO:
            self.user_data["workspace"]["current_view"] = "video"
        elif mode == WorkspaceMode.PDF:
            self.user_data["workspace"]["current_view"] = "pdf"
        else:
            self.user_data["workspace"]["current_view"] = "welcome"

        # Update recent files with latest position
        from immersion_app.core.recent_files import add_recent_file
        if mode == WorkspaceMode.PDF and self.current_pdf_path:
            add_recent_file(
                self.user_data,
                str(self.current_pdf_path),
                "pdf",
                {"page_index": self.current_page_index}
            )
        elif mode == WorkspaceMode.VIDEO and self.current_video_path:
            add_recent_file(
                self.user_data,
                str(self.current_video_path),
                "video",
                {"video_position_ms": self.media_player.position() if self.media_player else 0}
            )

        save_user_data(self.user_data)

    def _restore_last_session(self):
        session = self.user_data["last_session"]
        content_type = str(session.get("content_type") or "")
        pdf_path = str(session.get("pdf_path") or "")
        video_path = str(session.get("video_path") or "")

        logger.info(f"Restoring session: content_type={content_type}, pdf={pdf_path or 'none'}, video={video_path or 'none'}")

        def _try_video():
            if video_path and Path(video_path).exists():
                logger.info(f"Restoring video session: {video_path}")
                self.subtitle_offset_ms = int(session.get("subtitle_offset_ms") or 0)
                self._load_video(video_path, restore_position_ms=int(session.get("video_position_ms") or 0))
                srt_path = str(session.get("srt_path") or "")
                if srt_path and Path(srt_path).exists():
                    self._load_subtitles(srt_path)
                return True
            elif video_path:
                logger.warning(f"Video from last session not found: {video_path}")
            return False

        def _try_pdf():
            if pdf_path and Path(pdf_path).exists():
                logger.info(f"Restoring PDF session: {pdf_path}")
                self._load_pdf(pdf_path, initial_page_index=int(session.get("page_index") or 0))
                return True
            elif pdf_path:
                logger.warning(f"PDF from last session not found: {pdf_path}")
            return False

        if content_type == "pdf":
            if _try_pdf() or _try_video():
                return
        else:
            if _try_video() or _try_pdf():
                return

        logger.debug("No valid session to restore")
        if content_type in ("pdf", "video"):
            self.command_bar.set_mode(content_type)

    def closeEvent(self, event):
        self._persist_session()
        super().closeEvent(event)
