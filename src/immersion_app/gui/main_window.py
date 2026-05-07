"""Unified sentence mining workspace."""

from __future__ import annotations

import os
import re
import socket
import subprocess
from datetime import datetime
from pathlib import Path

import fitz
from PySide6.QtCore import QObject, QPoint, QRect, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QActionGroup, QImage, QIntValidator, QKeySequence, QPainter, QPen, QPixmap
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

from immersion_app.core.anki import add_anki_card, test_anki_connection
from immersion_app.core.language_config import (
    DEFAULT_LEARNING_LANGUAGE,
    DEFAULT_NATIVE_LANGUAGE,
    get_argos_language_code,
    get_google_language_code,
    get_language_label,
    get_whisper_language_code,
    list_language_codes,
    normalize_language_code,
)
from immersion_app.core.paths import DATA_ROOT, PROCESSED_LOG_PATH, QUEUE_JSON_PATH
from immersion_app.core.queue_store import append_processed_log, append_queue_entry, load_queue_entries, queue_count, save_queue_entries
from immersion_app.core.user_data import load_user_data, save_user_data
from immersion_app.gui.widgets.subtitle_widget import ClickableSubtitleLabel
from immersion_app.gui.widgets.command_bar import CommandBar
from immersion_app.gui.widgets.translation_popover import TranslationPopover
from immersion_app.gui.widgets.chapter_rail import ChapterRail
from immersion_app.gui.widgets.pdf_status_bar import PDFStatusBar
from immersion_app.gui.widgets.transport_bar import TransportBar
from immersion_app.gui.theme import Theme
from immersion_app.integrations.subtitle_generation import generate_srt_from_video
from immersion_app.integrations.translation_backends import OfflineTranslationBackend, OnlineTranslationBackend
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
            try:
                self.signals.failed.emit(self.request_id, str(exc))
            except RuntimeError:
                return


class AnkiStatusSignals(QObject):
    finished = Signal(int, bool)


class AnkiStatusTask(QRunnable):
    def __init__(self, request_id):
        super().__init__()
        self.request_id = request_id
        self.signals = AnkiStatusSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.request_id, test_anki_connection())
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

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LinguaLoop Workspace")
        self.resize(1680, 980)

        self.thread_pool = QThreadPool.globalInstance()
        self._subtitle_thread_pool = QThreadPool.globalInstance()
        self.current_request_id = 0
        self.anki_check_request_id = 0
        self.translation_cache = {}
        self._translation_cache_keys_by_request = {}
        self.user_data = load_user_data()
        self.analytics_vocabulary = set(self.user_data.get("analytics", {}).get("vocabulary_seen", []))

        self.selected_word = ""
        self.selected_sentence = ""
        self.selected_translation = ""
        self.current_source_type = ""
        self.current_source_name = ""
        self.current_source_location = ""
        self.is_anki_connected = False
        self.translation_mode = self.user_data["preferences"].get("translation_mode", "online")
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
        self.highlight_bboxes = []
        self.selection_anchor_key = None

        self.media_player = None
        self.audio_output = None
        self.current_video_path = ""
        self.current_srt_path = ""
        self.subtitle_parser = None
        self.current_subtitle = None
        self.subtitle_selection_anchor = None
        self.subtitle_offset_ms = int(self.user_data["last_session"].get("subtitle_offset_ms") or 0)
        self._is_slider_dragging = False

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

        # Command bar at top
        self.command_bar = CommandBar()
        self.command_bar.mode_changed.connect(self._on_mode_changed)
        self.command_bar.open_requested.connect(self._open_content_dialog)
        self.command_bar.close_requested.connect(self._close_current_file)
        self.command_bar.settings_requested.connect(self._show_settings_dialog)
        main_layout.addWidget(self.command_bar)

        # Workspace stack (Welcome/PDF/Video pages)
        self.workspace_stack = QStackedWidget()
        self.welcome_page = self._build_welcome_page()
        self.pdf_page = self._build_pdf_page()
        self.video_page = self._build_video_page()
        self.workspace_stack.addWidget(self.welcome_page)
        self.workspace_stack.addWidget(self.pdf_page)
        self.workspace_stack.addWidget(self.video_page)
        main_layout.addWidget(self.workspace_stack)

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

        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()

    def _setup_keyboard_shortcuts(self):
        """Setup global keyboard shortcuts."""
        # Mode switching
        pdf_mode_action = QAction("PDF Mode", self)
        pdf_mode_action.setShortcut(QKeySequence("Ctrl+1"))
        pdf_mode_action.triggered.connect(lambda: self._on_mode_changed("pdf"))
        self.addAction(pdf_mode_action)

        video_mode_action = QAction("Video Mode", self)
        video_mode_action.setShortcut(QKeySequence("Ctrl+2"))
        video_mode_action.triggered.connect(lambda: self._on_mode_changed("video"))
        self.addAction(video_mode_action)

        # File operations
        open_action = QAction("Open source", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_content_dialog)
        self.addAction(open_action)

        load_subs_action = QAction("Load subtitles", self)
        load_subs_action.setShortcut(QKeySequence("Ctrl+L"))
        load_subs_action.triggered.connect(self._open_subtitle_dialog)
        self.addAction(load_subs_action)

        # Study actions
        add_now_action = QAction("Add now", self)
        add_now_action.setShortcut(QKeySequence("Ctrl+Return"))
        add_now_action.triggered.connect(self._add_now)
        self.addAction(add_now_action)

        add_queue_action = QAction("Add to queue", self)
        add_queue_action.setShortcut(QKeySequence("Ctrl+Shift+Return"))
        add_queue_action.triggered.connect(self._add_to_queue)
        self.addAction(add_queue_action)

        # Video playback
        play_action = QAction("Play/Pause", self)
        play_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        play_action.triggered.connect(self._toggle_play_pause)
        self.addAction(play_action)

        # PDF navigation
        prev_page_action = QAction("Previous Page", self)
        prev_page_action.setShortcut(QKeySequence(Qt.Key.Key_Left))
        prev_page_action.triggered.connect(self._prev_page)
        self.addAction(prev_page_action)

        next_page_action = QAction("Next Page", self)
        next_page_action.setShortcut(QKeySequence(Qt.Key.Key_Right))
        next_page_action.triggered.connect(self._next_page)
        self.addAction(next_page_action)

        # PDF zoom
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setShortcut(QKeySequence("Ctrl++"))
        zoom_in_action.triggered.connect(self._zoom_in)
        self.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.triggered.connect(self._zoom_out)
        self.addAction(zoom_out_action)

        fit_width_action = QAction("Fit to Width", self)
        fit_width_action.setShortcut(QKeySequence("Ctrl+0"))
        fit_width_action.triggered.connect(self._fit_width)
        self.addAction(fit_width_action)

        # Close popover
        escape_action = QAction("Close Popover", self)
        escape_action.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        escape_action.triggered.connect(self._close_popover)
        self.addAction(escape_action)

    def _on_mode_changed(self, mode: str):
        """Handle mode change from command bar."""
        if mode == "pdf":
            if self.doc:
                self.workspace_stack.setCurrentWidget(self.pdf_page)
            else:
                self.workspace_stack.setCurrentWidget(self.welcome_page)
        elif mode == "video":
            if self.current_video_path:
                self.workspace_stack.setCurrentWidget(self.video_page)
            else:
                self.workspace_stack.setCurrentWidget(self.welcome_page)

    def _show_settings_dialog(self):
        """Show settings dialog (stub for now - will implement later)."""
        # TODO: Create a proper settings dialog
        menu = QMenu(self)

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
        menu.addAction("Generate subtitles", self._generate_subtitles_interactive)

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
        shortcuts = QLabel("Ctrl+O to open · Ctrl+1/2 to switch modes")
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

        # Left spacer
        main_layout.addStretch(1)

        # Central reading column (responsive width: 600-900px)
        reading_column = QWidget()
        reading_column.setMinimumWidth(Theme.READING_COLUMN_MIN_WIDTH)
        reading_column.setMaximumWidth(Theme.READING_COLUMN_MAX_WIDTH)
        reading_column.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        column_layout = QVBoxLayout(reading_column)
        column_layout.setContentsMargins(36, 36, 36, 36)
        column_layout.setSpacing(0)

        # PDF scroll area
        self.pdf_label = ClickablePdfLabel()
        self.pdf_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.pdf_label.clicked.connect(self._on_pdf_click)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setWidget(self.pdf_label)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {Theme.BG};
            }}
        """)
        column_layout.addWidget(self.scroll_area)

        main_layout.addWidget(reading_column)

        # Right spacer
        main_layout.addStretch(1)

        # Chapter rail (48px, right edge)
        self.chapter_rail = ChapterRail()
        self.chapter_rail.chapter_clicked.connect(self._on_chapter_clicked)
        main_layout.addWidget(self.chapter_rail)

        page_layout.addLayout(main_layout)

        # Status bar at bottom
        self.pdf_status_bar = PDFStatusBar()
        # Connect zoom signals
        self.pdf_status_bar.zoom_in_clicked.connect(self._zoom_in)
        self.pdf_status_bar.zoom_out_clicked.connect(self._zoom_out)
        self.pdf_status_bar.fit_width_clicked.connect(self._fit_width)
        self.pdf_status_bar.reset_zoom_clicked.connect(self._reset_zoom)
        page_layout.addWidget(self.pdf_status_bar)

        # Keep page_input for programmatic use (hidden from UI)
        self.page_input = QLineEdit()
        self.page_input.setValidator(QIntValidator(1, 1, self))
        self.page_input.setVisible(False)

        # Page info label (legacy, hidden)
        self.page_info_label = QLabel("No PDF loaded")
        self.page_info_label.setVisible(False)

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
        layout.addWidget(self.video_widget, stretch=1)

        # Subtitle overlay (positioned at bottom, above transport bar)
        self.subtitle_label = ClickableSubtitleLabel(page, vocabulary_seen=self.analytics_vocabulary)
        self.subtitle_label.setFixedHeight(80)
        self.subtitle_label.clicked.connect(self._on_subtitle_click)
        self.subtitle_label.setStyleSheet("""
            ClickableSubtitleLabel {
                background-color: transparent;
            }
        """)
        layout.addWidget(self.subtitle_label)

        # Transport bar with full controls
        self.transport_bar = TransportBar()
        self.transport_bar.play_pause_clicked.connect(self._toggle_play_pause)
        self.transport_bar.replay_clicked.connect(self._replay_subtitle)
        self.transport_bar.slider_pressed.connect(self._on_slider_pressed)
        self.transport_bar.slider_released.connect(self._on_slider_released)
        self.transport_bar.slider_moved.connect(self._on_slider_moved)
        self.transport_bar.speed_changed.connect(self._on_speed_changed)
        self.transport_bar.volume_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self.transport_bar)

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
        # TODO: Show message in a toast notification or status area

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
        if self._check_internet_connection() and OnlineTranslationBackend().is_available():
            if self.translation_mode != "offline":
                self.translation_mode = "online"
        elif OfflineTranslationBackend().is_available():
            self.translation_mode = "offline"
        self._update_translation_status_label()

    def _update_translation_status_label(self):
        if self.translation_mode == "offline":
            self.translation_status_label.setText("Translation: Offline")
            self.mode_indicator_label.setText("Translation mode: OFFLINE")
        else:
            self.translation_status_label.setText("Translation: Online")
            self.mode_indicator_label.setText("Translation mode: ONLINE")
        self.user_data["preferences"]["translation_mode"] = self.translation_mode
        save_user_data(self.user_data)

    def _toggle_translation_mode(self):
        if self.translation_mode == "online":
            if not OfflineTranslationBackend().is_available():
                self._set_status("Offline translation backend is not installed.")
                return
            self.translation_mode = "offline"
        else:
            if not OnlineTranslationBackend().is_available():
                self._set_status("Online translation backend is not installed.")
                return
            self.translation_mode = "online"
        self._update_translation_status_label()

    def _get_translation_language_codes(self):
        if self.translation_mode == "offline":
            return (
                get_argos_language_code(self.learning_language),
                get_argos_language_code(self.native_language),
            )
        return (
            get_google_language_code(self.learning_language),
            get_google_language_code(self.native_language),
        )

    def _set_learning_language(self, code):
        self.learning_language = normalize_language_code(code, DEFAULT_LEARNING_LANGUAGE)
        self.translation_cache.clear()
        self.user_data["preferences"]["learning_language"] = self.learning_language
        save_user_data(self.user_data)
        self._set_status(f"Learning language: {get_language_label(self.learning_language)}")

    def _set_native_language(self, code):
        self.native_language = normalize_language_code(code, DEFAULT_NATIVE_LANGUAGE)
        self.translation_cache.clear()
        self.user_data["preferences"]["native_language"] = self.native_language
        save_user_data(self.user_data)
        self._set_status(f"Native language: {get_language_label(self.native_language)}")

    def _request_translation(self, text):
        if not text:
            return
        key = (self.learning_language, self.native_language, text)
        if key in self.translation_cache:
            self.selected_translation = self.translation_cache[key]
            self._update_selection_panel()
            self._update_action_buttons()
            return

        self.current_request_id += 1
        request_id = self.current_request_id
        self.selected_translation = "Translating..."
        self._update_selection_panel()
        self._update_action_buttons()
        backend = OnlineTranslationBackend() if self.translation_mode == "online" else OfflineTranslationBackend()
        src_lang, dest_lang = self._get_translation_language_codes()
        task = TranslateTask(request_id, text, src_lang, dest_lang, backend)
        self._translation_cache_keys_by_request[request_id] = key
        task.signals.finished.connect(self._on_translation_done)
        task.signals.failed.connect(self._on_translation_failed)
        self.thread_pool.start(task)

    def _on_translation_done(self, request_id, source_text, translated_text):
        if request_id != self.current_request_id:
            return
        key = self._translation_cache_keys_by_request.pop(
            request_id, (self.learning_language, self.native_language, source_text)
        )
        self.translation_cache[key] = translated_text
        self.selected_translation = translated_text
        self._update_selection_panel()
        self._update_action_buttons()

    def _on_translation_failed(self, request_id, error_message):
        if request_id != self.current_request_id:
            return
        self._translation_cache_keys_by_request.pop(request_id, None)
        self.selected_translation = f"Translation error: {error_message}"
        self._update_selection_panel()
        self._update_action_buttons()
        self._set_status(f"Translation failed: {error_message}")

    def _translate_word_field_input(self):
        text = self.word_value.text().strip()
        if not text:
            self.selected_word = ""
            self.selected_translation = ""
            self._update_selection_panel()
            self._update_action_buttons()
            return
        self.selected_word = text
        self._request_translation(text)

    def _update_selection_panel(self):
        """Update legacy selection panel and show translation popover."""
        # Update legacy widgets (for backward compatibility)
        if self.word_value.text() != self.selected_word:
            self.word_value.setText(self.selected_word)
        self.sentence_value.setText(self.selected_sentence)
        self.translation_value.setText(self.selected_translation)
        if self.current_source_name:
            self.source_header_label.setText(
                f"{self.current_source_name} | {self.current_source_location or 'location unavailable'}"
            )
        else:
            self.source_header_label.setText("Nothing selected")

        # Update and show popover if we have a selection
        if self.selected_word and self.selected_translation:
            self._show_translation_popover()

    def _update_action_buttons(self):
        has_selection = bool(self.selected_word)
        has_translation = bool(
            self.selected_translation and not self.selected_translation.startswith("Translation error:")
        )
        self.add_now_button.setEnabled(has_selection and has_translation)
        self.add_queue_button.setEnabled(has_selection and has_translation)

    def _clear_selection_state(self):
        self.selected_word = ""
        self.selected_sentence = ""
        self.selected_translation = ""
        self._update_selection_panel()
        self._update_action_buttons()
        # Close popover if open
        if self.translation_popover.isVisible():
            self.translation_popover.close()

    def _show_translation_popover(self):
        """Show translation popover near the selected word."""
        # Only show if we have valid translation
        if not self.selected_translation or self.selected_translation.startswith("Translation error:"):
            return

        # Set popover content
        self.translation_popover.set_content(
            word=self.selected_word,
            meaning=self.selected_translation,
            sentence=self.selected_sentence,
            sentence_translation="",  # TODO: Get sentence translation if available
            metadata=""  # TODO: Add POS/IPA if available
        )

        # Position near the clicked word
        # For PDF: use highlight_bboxes to get word position
        # For video: use subtitle label position
        if self.current_source_type == "pdf" and self.highlight_bboxes:
            # Get first bbox and convert to global coordinates
            bbox = self.highlight_bboxes[0]
            x_screen = int(bbox[0] * self.zoom_factor)
            y_screen = int(bbox[1] * self.zoom_factor)

            # Convert from PDF label coordinates to global screen coordinates
            pdf_point = self.pdf_label.mapToGlobal(QPoint(x_screen, y_screen))
            word_rect = QRect(
                pdf_point.x(),
                pdf_point.y(),
                int((bbox[2] - bbox[0]) * self.zoom_factor),
                int((bbox[3] - bbox[1]) * self.zoom_factor)
            )
            self.translation_popover.position_near_word(word_rect)
            self.translation_popover.show_animated()

        elif self.current_source_type == "video":
            # Position near subtitle label
            subtitle_global_pos = self.subtitle_label.mapToGlobal(QPoint(0, 0))
            word_rect = QRect(
                subtitle_global_pos.x() + self.subtitle_label.width() // 2 - 50,
                subtitle_global_pos.y(),
                100,
                self.subtitle_label.height()
            )
            self.translation_popover.position_near_word(word_rect)
            self.translation_popover.show_animated()

    def _on_popover_edit_requested(self):
        """Handle edit request from popover."""
        # TODO: Implement edit flow - expand popover or show edit dialog
        pass

    def _on_popover_closed(self):
        """Handle popover close event."""
        # Optionally clear selection or keep it
        pass

    def _close_popover(self):
        """Close the translation popover if visible."""
        if self.translation_popover.isVisible():
            self.translation_popover.close()

    def _update_command_bar_stats(self):
        """Update the stats chip in the command bar."""
        total_count = len(self.analytics_vocabulary)
        # TODO: Calculate today_count when we add timestamps to vocabulary
        today_count = 0
        self.command_bar.set_stats(today_count, total_count)

    def _on_chapter_clicked(self, page_number):
        """Navigate to a chapter when clicked in the chapter rail."""
        if self.doc and 1 <= page_number <= self.doc.page_count:
            self.current_page_index = page_number - 1
            self.highlight_bboxes = []
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
        self.anki_status_label.setText("Anki: checking...")
        task = AnkiStatusTask(request_id)
        task.signals.finished.connect(self._on_anki_status_checked)
        self.thread_pool.start(task)

    def _on_anki_status_checked(self, request_id, connected):
        if request_id != self.anki_check_request_id:
            return
        self.is_anki_connected = connected
        self.anki_status_label.setText("Anki: connected" if connected else "Anki: not connected")
        self.health_label.setText(
            f"Anki: {'ready' if connected else 'not connected'}\nTranslation backend: {self.translation_mode}"
        )

    def _start_anki(self):
        if not os.path.exists(ANKI_PATH):
            QMessageBox.warning(self, "Anki Not Found", f"Anki executable not found at:\n{ANKI_PATH}")
            return
        try:
            self.anki_process = subprocess.Popen([ANKI_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            QMessageBox.critical(self, "Start Anki Failed", str(exc))
            return
        self._set_status("Anki started. Checking connection...")
        QTimer.singleShot(3500, self._refresh_anki_status)

    def _build_note_sentence(self):
        sentence = self.selected_sentence or self.selected_word
        if sentence in self.sentence_counts:
            self.sentence_counts[sentence] += 1
            return f"{sentence} ({self.sentence_counts[sentence]})"
        self.sentence_counts[sentence] = 1
        return sentence

    def _record_successful_card_add(self, word_text):
        analytics = self.user_data["analytics"]
        analytics["cards_added_total"] = int(analytics.get("cards_added_total") or 0) + 1
        self.analytics_vocabulary.update(token.lower() for token in re.findall(r"\b\w+\b", word_text, flags=re.UNICODE))
        analytics["vocabulary_seen"] = sorted(self.analytics_vocabulary)
        save_user_data(self.user_data)

        # Update UI to reflect new vocabulary state
        self.subtitle_label.set_vocabulary_seen(self.analytics_vocabulary)
        self._update_command_bar_stats()

        # Re-render PDF to update word highlighting
        if self.doc and self.current_source_type == "pdf":
            self._render_current_page()

    def _queue_payload(self):
        return {
            "sentence": self.selected_sentence or self.selected_word,
            "word": self.selected_word,
            "translation": self.selected_translation,
            "source_name": self.current_source_name,
            "source_type": self.current_source_type,
            "location": self.current_source_location,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "status": "queued",
        }

    def _add_now(self):
        if not self.selected_word or not self.selected_translation:
            return
        if not self.is_anki_connected:
            QMessageBox.warning(self, "Anki Not Connected", "AnkiConnect is not available.")
            return
        try:
            note_id = add_anki_card(self._build_note_sentence(), self.selected_word, self.selected_translation)
            self._record_successful_card_add(self.selected_word)
            self._set_status(f"Added card to Anki (Note ID: {note_id})")
        except Exception as exc:
            QMessageBox.critical(self, "Anki Add Failed", str(exc))

    def _add_to_queue(self):
        if not self.selected_word or not self.selected_translation:
            return
        try:
            append_queue_entry(self._queue_payload())
            self._refresh_queue_summary()
            self._set_status(f"Queued '{self.selected_word}'")
        except Exception as exc:
            QMessageBox.critical(self, "Queue Write Failed", str(exc))

    def _process_queue(self):
        entries = load_queue_entries()
        if not entries:
            QMessageBox.information(self, "Queue Empty", "No queued cards found.")
            return
        if not self.is_anki_connected:
            QMessageBox.warning(self, "Anki Not Connected", "AnkiConnect is not available.")
            return

        successful_entries = []
        failed_entries = []
        for entry in entries:
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
            except Exception:
                failed_entries.append(entry)

        if successful_entries:
            append_processed_log(successful_entries)
        save_queue_entries(failed_entries)
        self._refresh_queue_summary()
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
        self.current_source_type = ""
        self.current_source_name = ""
        self._clear_selection_state()
        self.workspace_stack.setCurrentWidget(self.welcome_page)
        self.command_bar.set_title("No document loaded")
        self.command_bar.set_file_loaded(False)
        self._persist_session()

    def _load_pdf(self, path, initial_page_index=0):
        try:
            self.doc = fitz.open(path)
        except Exception as exc:
            QMessageBox.critical(self, "PDF Error", f"Failed to open PDF:\n{exc}")
            return

        self.current_pdf_path = path
        self.current_page_index = max(0, min(initial_page_index, self.doc.page_count - 1))
        self.page_input.setValidator(QIntValidator(1, self.doc.page_count, self))
        self.current_source_type = "pdf"
        self.current_source_name = Path(path).name
        self.current_source_location = f"Page {self.current_page_index + 1}"
        self.workspace_stack.setCurrentWidget(self.pdf_page)
        self._clear_selection_state()
        self.highlight_bboxes = []
        self.selection_anchor_key = None
        self._render_current_page()
        self._update_source_summary()
        self._persist_session()
        self._set_status(f"Opened PDF: {Path(path).name}")

        # Update command bar
        self.command_bar.set_title(
            Path(path).name,
            f"{self.doc.page_count} pages"
        )
        self.command_bar.set_mode("pdf")
        self.command_bar.set_file_loaded(True)
        self._update_command_bar_stats()

        # Update chapter rail with PDF outline
        try:
            toc = self.doc.get_toc()
            self.chapter_rail.set_chapters(toc, self.doc.page_count)
        except Exception:
            self.chapter_rail.set_chapters([], self.doc.page_count)

    def _render_current_page(self):
        if not self.doc:
            self.page_info_label.setText("No PDF loaded")
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
        if self.highlight_bboxes:
            selection_color = Theme.to_qcolor(Theme.HL_SELECTED)
            for x0, y0, x1, y1 in self.highlight_bboxes:
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
        self.page_info_label.setText(
            f"{Path(self.current_pdf_path).name} | Page {self.current_page_index + 1}/{self.doc.page_count} | Zoom {self.zoom_factor:.2f}x"
        )
        self.page_input.setText(str(self.current_page_index + 1))
        self.current_source_location = f"Page {self.current_page_index + 1}"
        self._update_source_summary()

        # Update chapter rail
        self.chapter_rail.set_current_page(self.current_page_index + 1)

        # Update zoom display in status bar
        self.pdf_status_bar.set_zoom_level(self.zoom_factor)

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
            return

        shift_pressed = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        selected_words = self._resolve_selected_words(hit_word, shift_pressed)
        cleaned_words = [self._clean_word(selected[4]) for selected in selected_words if self._clean_word(selected[4])]
        if not cleaned_words:
            return
        self.highlight_bboxes = [(w[0], w[1], w[2], w[3]) for w in selected_words]
        self.selected_word = " ".join(cleaned_words)
        self.selected_sentence = self._extract_context_for_selection(selected_words)
        self.selected_translation = "Translating..."
        self.current_source_type = "pdf"
        self.current_source_location = f"Page {self.current_page_index + 1}"
        self._update_selection_panel()
        self._update_action_buttons()
        self._render_current_page()
        self._request_translation(self.selected_word)

    def _resolve_selected_words(self, hit_word, shift_pressed):
        hit_key = self._word_key(hit_word)
        if not shift_pressed or self.selection_anchor_key is None:
            self.selection_anchor_key = hit_key
            return [hit_word]
        anchor_index = self.page_word_index.get(self.selection_anchor_key)
        hit_index = self.page_word_index.get(hit_key)
        if anchor_index is None or hit_index is None:
            self.selection_anchor_key = hit_key
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
        self.highlight_bboxes = []
        self._clear_selection_state()
        self._render_current_page()
        self._persist_session()

    def _next_page(self):
        if not self.doc or self.current_page_index >= self.doc.page_count - 1:
            return
        self.current_page_index += 1
        self.highlight_bboxes = []
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

    def _go_to_page(self):
        if not self.doc:
            return
        try:
            requested_page = int(self.page_input.text().strip())
        except ValueError:
            self._set_status("Invalid page number")
            return
        if requested_page < 1 or requested_page > self.doc.page_count:
            self._set_status(f"Page must be between 1 and {self.doc.page_count}")
            return
        self.current_page_index = requested_page - 1
        self.highlight_bboxes = []
        self._clear_selection_state()
        self._render_current_page()
        self._persist_session()

    def _open_subtitle_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load subtitles", "", "SRT Files (*.srt)")
        if not path:
            return
        self._load_subtitles(path)

    def _load_video(self, path, restore_position_ms=0):
        """Load video with validation and error handling."""
        # Validate file exists
        video_path = Path(path)
        if not video_path.exists():
            QMessageBox.critical(self, "File Not Found", f"Video file does not exist:\n{path}")
            return

        # Validate file size (detect empty/corrupt files)
        if video_path.stat().st_size < 1024:  # Less than 1KB
            QMessageBox.warning(
                self,
                "Invalid File",
                f"Video file appears to be empty or corrupted:\n{video_path.name}"
            )
            return

        # Continue with existing loading logic...
        self.current_video_path = path
        self.current_source_type = "video"
        self.current_source_name = Path(path).name
        self.current_source_location = "00:00"
        self.workspace_stack.setCurrentWidget(self.video_page)
        self.media_player.setSource(QUrl.fromLocalFile(path))
        if restore_position_ms > 0:
            QTimer.singleShot(400, lambda: self.media_player.setPosition(restore_position_ms))

        auto_srt = find_best_srt_for_video(path)
        if auto_srt:
            self._load_subtitles(auto_srt)
        else:
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
        self.command_bar.set_mode("video")
        self.command_bar.set_file_loaded(True)
        self._update_command_bar_stats()

    def _load_subtitles(self, srt_path):
        try:
            self.subtitle_parser = SRTParser.from_file(srt_path)
            self.current_srt_path = srt_path
            self._persist_session()
            self._set_status(f"Loaded subtitles: {Path(srt_path).name}")
        except Exception as exc:
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
        self.selected_word = " ".join(cleaned_words)
        self.selected_sentence = self.current_subtitle.text
        self.selected_translation = "Translating..."
        self.current_source_type = "video"
        self.current_source_location = self._fmt_ms(self.media_player.position())
        self.subtitle_label.highlight_word_range(selected_indices[0], selected_indices[-1])
        self._update_selection_panel()
        self._update_action_buttons()
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
        anchor_index = max(0, min(self.subtitle_selection_anchor[1], token_count - 1))
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
            self.subtitle_selection_anchor = None
            self.subtitle_label.set_subtitle(None)
            return
        lookup_position = max(0, position - self.subtitle_offset_ms)
        subtitle = self.subtitle_parser.get_subtitle_at_time(lookup_position)
        if subtitle is None:
            self.current_subtitle = None
            self.subtitle_selection_anchor = None
            self.subtitle_label.set_subtitle(None)
            return
        if self.current_subtitle is None or subtitle.index != self.current_subtitle.index:
            self.current_subtitle = subtitle
            self.subtitle_selection_anchor = None
            self.subtitle_label.set_subtitle(subtitle)

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
        print(f"[VIDEO ERROR] {error}: {error_string} | File: {self.current_video_path}")

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

        print(f"[VIDEO STATUS] Media status: {status}")

        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            file_name = Path(self.current_video_path).name if self.current_video_path else "Unknown"
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
            f"Type: {self.current_source_type or 'none'}\n"
            f"Location: {self.current_source_location or 'n/a'}\n"
            f"Subtitles: {subtitle_state}"
        )

    def _persist_session(self):
        session = self.user_data["last_session"]
        session.update(
            {
                "content_type": self.current_source_type,
                "pdf_path": self.current_pdf_path,
                "page_index": int(self.current_page_index),
                "video_path": self.current_video_path,
                "video_position_ms": int(self.media_player.position() if self.media_player else 0),
                "srt_path": self.current_srt_path,
                "subtitle_offset_ms": int(self.subtitle_offset_ms),
            }
        )
        if self.workspace_stack.currentWidget() == self.video_page:
            self.user_data["workspace"]["current_view"] = "video"
        elif self.workspace_stack.currentWidget() == self.pdf_page:
            self.user_data["workspace"]["current_view"] = "pdf"
        else:
            self.user_data["workspace"]["current_view"] = "welcome"
        save_user_data(self.user_data)

    def _restore_last_session(self):
        session = self.user_data["last_session"]
        pdf_path = str(session.get("pdf_path") or "")
        video_path = str(session.get("video_path") or "")
        if video_path and Path(video_path).exists():
            self.subtitle_offset_ms = int(session.get("subtitle_offset_ms") or 0)
            self._load_video(video_path, restore_position_ms=int(session.get("video_position_ms") or 0))
            srt_path = str(session.get("srt_path") or "")
            if srt_path and Path(srt_path).exists():
                self._load_subtitles(srt_path)
            return
        if pdf_path and Path(pdf_path).exists():
            self._load_pdf(pdf_path, initial_page_index=int(session.get("page_index") or 0))

    def closeEvent(self, event):
        self._persist_session()
        super().closeEvent(event)
