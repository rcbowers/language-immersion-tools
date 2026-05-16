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
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence, QPainter, QPen, QPixmap
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

from immersion_app.core.anki import add_anki_card
from immersion_app.core.anki_analytics import AnkiAnalyticsManager
from immersion_app.core.anki_service import AnkiService
from immersion_app.core.anki_snapshot import load_snapshot, save_snapshot
from immersion_app.core.appearance_manager import AppearanceManager, AppearanceMode
from immersion_app.core.completion_tracker import CompletionTracker
from immersion_app.core.content_browser_manager import ContentBrowserManager
from immersion_app.core.preview_generator import PreviewGenerator
from immersion_app.core.usage_time_tracker import UsageTimeTracker
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
from immersion_app.core.pdf_service import PDFService
from immersion_app.core.selection_state import SelectionState
from immersion_app.core.shortcuts import ShortcutManager
from immersion_app.core.translation_service import TranslationService
from immersion_app.core.video_service import VideoService
from immersion_app.core.paths import DATA_ROOT, PROCESSED_LOG_PATH, QUEUE_JSON_PATH
from immersion_app.core.queue_store import append_processed_log, append_queue_entry, load_queue_entries, queue_count, save_queue_entries
from immersion_app.core.user_data import load_user_data, save_user_data
from immersion_app.gui.controllers import MiningController, PDFController, VideoController, WorkspaceController
from immersion_app.gui.widgets.card_feedback_toast import CardFeedbackToast
from immersion_app.gui.widgets.pdf_clickable_label import ClickablePdfLabel as PdfClickableLabelWidget
from immersion_app.gui.widgets.queue_dialog import QueueDialog as QueueDialogWidget
from immersion_app.gui.widgets.subtitle_widget import ClickableSubtitleLabel
from immersion_app.gui.widgets.command_bar import CommandBar
from immersion_app.gui.widgets.subtitle_generator_dialog import SubtitleGeneratorDialog as SubtitleGeneratorDialogWidget
from immersion_app.gui.widgets.translation_popover import TranslationPopover
from immersion_app.gui.widgets.pdf_status_bar import PDFStatusBar
from immersion_app.gui.widgets.shortcut_panel import ShortcutPanel
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
    hovered = Signal(QPoint, object)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(event.position().toPoint(), event.modifiers())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.hovered.emit(event.position().toPoint(), event.modifiers())
        super().mouseMoveEvent(event)


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

    def refresh_theme(self):
        self.setStyleSheet(f"QDialog {{ background-color: {Theme.BG}; }}")
        self.language_input.setStyleSheet(Theme.get_input_style())
        self.status_label.setStyleSheet(Theme.get_label_style("caption"))

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
            {Theme.get_scrollbar_style()}
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

    def refresh_theme(self):
        self.setStyleSheet(f"QDialog {{ background-color: {Theme.BG}; }}")
        self.summary_label.setStyleSheet(Theme.get_label_style("body"))
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {Theme.SURFACE};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 8px;
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 13px;
                color: {Theme.TEXT};
            }}
            QListWidget::item {{
                padding: 8px;
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {Theme.SURFACE_ALT};
            }}
            {Theme.get_scrollbar_style()}
        """)
        self.process_button.setStyleSheet(Theme.get_button_style("primary"))

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
        self._next_translation_request_id = 0
        self.translation_cache = {}
        self._translation_requests = {}
        self._translation_requests_by_key = {}
        self._translation_context_version = 0
        self._online_backend = None
        self._offline_backend = None
        self._cache_hits = 0
        self._cache_misses = 0
        self.user_data = load_user_data()
        self.appearance_manager = AppearanceManager(
            self.user_data["preferences"].get("theme_mode", AppearanceMode.LIGHT.value)
        )
        Theme.apply_mode(self.appearance_manager.mode_string())
        snapshot_words = load_snapshot()
        self.anki_analytics = AnkiAnalyticsManager(self.user_data, snapshot_words=snapshot_words)
        self.analytics_vocabulary = set(self.anki_analytics.vocabulary_seen)
        logger.info(f"Analytics vocabulary initialized with {len(self.analytics_vocabulary)} words ({len(snapshot_words)} from snapshot)")

        # Log startup configuration
        logger.info("=" * 60)
        logger.info("LinguaLoop Workspace - Application Startup")
        logger.info("=" * 60)
        logger.info(f"Learning Language: {self.user_data['preferences']['learning_language']}")
        logger.info(f"Native Language: {self.user_data['preferences']['native_language']}")
        logger.info(f"Translation Mode: {self.user_data['preferences']['translation_mode']}")
        logger.info(f"Theme Mode: {self.user_data['preferences'].get('theme_mode', 'light')}")
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
        self.anki_service = AnkiService(thread_pool=self.thread_pool, parent=self)
        self.translation_service = TranslationService(
            learning_language=self.user_data["preferences"].get("learning_language", DEFAULT_LEARNING_LANGUAGE),
            native_language=self.user_data["preferences"].get("native_language", DEFAULT_NATIVE_LANGUAGE),
            mode=self.user_data["preferences"].get("translation_mode", "offline"),
            thread_pool=self.thread_pool,
            parent=self,
        )
        self.pdf_service = PDFService(parent=self)
        self.video_service = VideoService(
            subtitle_offset_ms=int(self.user_data["last_session"].get("subtitle_offset_ms") or 0),
            parent=self,
        )
        self.completion_tracker = CompletionTracker(self.user_data)
        self.content_browser_manager = ContentBrowserManager(self.user_data)
        self.preview_generator = PreviewGenerator(Path.home() / ".lingua-loop" / "data" / "previews")

        # Initialize usage time tracker and connect to service signals
        self.usage_tracker = UsageTimeTracker(self.user_data)
        self.pdf_service.document_loaded.connect(self.usage_tracker.on_document_loaded)
        self.pdf_service.document_closed.connect(self.usage_tracker.on_document_closed)
        self.video_service.subtitles_loaded.connect(self._on_video_loaded_for_usage)
        self.video_service.subtitles_cleared.connect(self.usage_tracker.on_video_closed)
        self.selection.selection_changed.connect(lambda: self.usage_tracker.record_activity())
        self.translation_service.translation_ready.connect(lambda *_: self.usage_tracker.record_activity())
        self.usage_tracker.active_status_changed.connect(self._on_usage_tracking_status_changed)

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
        self.mining_controller = MiningController(
            self,
            self.selection,
            self.translation_service,
            self.anki_service,
            self.anki_analytics,
            parent=self,
        )
        self.pdf_controller = PDFController(self, self.pdf_service, self.selection, self.mining_controller, self.content_browser_manager)
        self.video_controller = VideoController(self, self.video_service, self.mining_controller, self.content_browser_manager)
        self.workspace_controller = WorkspaceController(self, self.pdf_controller, self.video_controller)
        self.appearance_manager.appearance_changed.connect(self._on_appearance_changed)
        self._bind_anki_service()
        self.anki_analytics.stats_changed.connect(self._on_anki_analytics_changed)
        self._determine_translation_mode()
        self._refresh_anki_status()
        self.workspace_controller.restore_last_session()
        self._refresh_queue_summary()
        self._update_command_bar_stats()
        self._apply_theme(refresh_pdf=False)

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

        # Create shortcut panel
        self.shortcut_panel = ShortcutPanel(
            self.mode_manager,
            self.completion_tracker,
            parent=self
        )
        self.shortcut_panel.hide()  # Start hidden

        # Connect panel signals
        self.shortcut_panel.page_completed.connect(self._on_page_completion_toggled)
        self.shortcut_panel.quick_add_requested.connect(self._add_now)
        self.shortcut_panel.queue_requested.connect(self._show_queue_dialog)
        self.shortcut_panel.theme_toggle_requested.connect(
            self.appearance_manager.toggle_mode
        )

        # Connect tracker signals to panel
        self.completion_tracker.completion_changed.connect(
            self._on_completion_changed_from_tracker
        )

        # Connect mode changes to panel visibility
        self.mode_manager.mode_changed.connect(self._update_shortcut_panel_visibility)

        # Connect appearance changes to panel
        self.appearance_manager.appearance_changed.connect(
            self.shortcut_panel.refresh_theme
        )

        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()

        # Connect mode manager signals
        self.mode_manager.mode_changed.connect(self._on_mode_changed_internal)
        self.mode_manager.mode_transition_failed.connect(self._on_mode_transition_failed)

    def _on_appearance_changed(self, mode: str):
        logger.info(f"Appearance changed to {mode}")
        Theme.apply_mode(mode)
        self.user_data["preferences"]["theme_mode"] = mode
        save_user_data(self.user_data)
        self._apply_theme(refresh_pdf=True)

    def _apply_theme(self, refresh_pdf: bool = True):
        self.setStyleSheet(f"QMainWindow {{ background-color: {Theme.BG}; }}")
        if hasattr(self, "command_bar"):
            self.command_bar.refresh_theme()
        if hasattr(self, "translation_popover"):
            self.translation_popover.refresh_theme()
        if hasattr(self, "card_feedback_toast"):
            self.card_feedback_toast.refresh_theme()
        if hasattr(self, "shortcut_panel"):
            self.shortcut_panel.refresh_theme()
        if hasattr(self, "welcome_page"):
            self._refresh_welcome_page_theme()
        if hasattr(self, "pdf_page"):
            self._refresh_pdf_page_theme()
        if hasattr(self, "video_page"):
            self._refresh_video_page_theme()
        if self.queue_dialog is not None:
            self.queue_dialog.refresh_theme()
        if self.doc and refresh_pdf:
            self._render_current_page()

    def _refresh_welcome_page_theme(self):
        self.welcome_page.setStyleSheet(f"QWidget {{ background-color: {Theme.BG}; }}")
        self.welcome_title_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: {Theme.FONT_SIZE_TITLE};
                font-weight: {Theme.FONT_WEIGHT_SEMIBOLD};
                margin-bottom: 12px;
            }}
        """)
        self.welcome_subtitle_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_SOFT};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 15px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
                margin-bottom: 32px;
            }}
        """)
        self.welcome_recent_heading.setStyleSheet(f"""
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
        self.welcome_recent_files_list.refresh()
        self.welcome_recent_files_list.refresh_theme()
        self.welcome_browser_heading.setStyleSheet(f"""
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
        self.content_browser_grid.refresh_theme()
        self.welcome_open_button.setStyleSheet(Theme.get_button_style("primary"))
        self.welcome_queue_button.setStyleSheet(Theme.get_button_style("secondary"))
        self.welcome_shortcuts_label.setStyleSheet(f"""
            QLabel {{
                color: {Theme.TEXT_MUTED};
                font-family: {Theme.FONT_FAMILY}, {Theme.FONT_FALLBACK};
                font-size: 12px;
                font-weight: {Theme.FONT_WEIGHT_REGULAR};
                margin-top: 48px;
            }}
        """)

    def _refresh_pdf_page_theme(self):
        self.pdf_page.setStyleSheet(f"QWidget {{ background-color: {Theme.BG}; }}")
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {Theme.BG};
            }}
            {Theme.get_scrollbar_style()}
        """)
        self.pdf_status_bar.refresh_theme()

    def _refresh_video_page_theme(self):
        self.video_page.setStyleSheet("QWidget { background-color: black; }")
        self.subtitle_label.setStyleSheet("""
            ClickableSubtitleLabel {
                background-color: transparent;
            }
        """)
        self.transport_bar.refresh_theme()

    def _bind_anki_service(self):
        """Bind Anki service state changes into window UI updates."""
        self.anki_service.status_check_started.connect(self._on_anki_status_check_started)
        self.anki_service.connection_changed.connect(self._on_anki_connection_changed)
        self.anki_service.vocabulary_loaded.connect(self._on_anki_vocabulary_loaded)

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
        elif event.type() == QEvent.Type.ActivationChange:
            # Track window focus for usage time tracking
            is_active = self.isActiveWindow()
            if hasattr(self, 'usage_tracker'):
                self.usage_tracker.set_window_focused(is_active)

    def _reposition_overlays(self):
        """Reposition all floating overlays based on current window geometry."""
        self._position_card_feedback_toast()
        if self.translation_popover.isVisible():
            self.translation_popover.reposition_from_stored_anchor()
        if hasattr(self, 'shortcut_panel') and self.shortcut_panel.isVisible():
            self.shortcut_panel.position_on_parent()

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

        # PDF: Quick add to Anki
        quick_add_action = QAction("Quick Add to Anki", self)
        quick_add_action.setShortcut(QKeySequence("Ctrl+Space"))
        quick_add_action.triggered.connect(self._add_now)
        self.addAction(quick_add_action)
        self.shortcut_manager.add_shortcut('pdf', quick_add_action)

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

    def _on_recent_file_selected(self, file_path: str, file_type: str):
        self.workspace_controller.on_recent_file_selected(file_path, file_type)

    def _on_browser_content_selected(self, file_path: str):
        """Handle content selection from browser grid."""
        # Get content metadata to determine type and last position
        content_item = self.content_browser_manager.get_content_by_path(file_path)
        if not content_item:
            return

        content_type = content_item.get("type", "")
        last_position = content_item.get("last_position", {})

        if content_type == "pdf":
            initial_page = last_position.get("page_index", 0)
            self.pdf_controller.load_pdf(file_path, initial_page_index=initial_page)
        elif content_type == "video":
            restore_position = last_position.get("video_position_ms", 0)
            self.video_controller.load_video(file_path, restore_position_ms=restore_position)

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
        menu.setStyleSheet(Theme.get_menu_style())
        current_mode = self.mode_manager.current_mode

        menu.addAction("Toggle translation mode", self._toggle_translation_mode)
        menu.addSeparator()

        appearance_menu = menu.addMenu("Appearance")
        appearance_menu.setStyleSheet(Theme.get_menu_style())
        appearance_group = QActionGroup(self)
        appearance_group.setExclusive(True)
        for label, mode in (("Light", AppearanceMode.LIGHT.value), ("Dark", AppearanceMode.DARK.value)):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(self.appearance_manager.mode_string() == mode)
            action.triggered.connect(lambda checked=False, theme_mode=mode: self._set_appearance_mode(theme_mode))
            appearance_group.addAction(action)
            appearance_menu.addAction(action)

        learning_menu = menu.addMenu("Learning language")
        learning_menu.setStyleSheet(Theme.get_menu_style())
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
        native_menu.setStyleSheet(Theme.get_menu_style())
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
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Title
        self.welcome_title_label = QLabel("Open a PDF or video to start")
        self.welcome_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.welcome_title_label)

        # Subtitle
        self.welcome_subtitle_label = QLabel("Click any word to see translations and build your vocabulary")
        self.welcome_subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.welcome_subtitle_label)

        layout.addSpacing(12)

        # Recent files section
        from immersion_app.gui.widgets.welcome_recent_files import WelcomeRecentFilesList
        recent_container = QWidget()
        recent_layout = QVBoxLayout(recent_container)
        recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.setSpacing(4)

        # Section heading
        self.welcome_recent_heading = QLabel("Recent")
        self.welcome_recent_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recent_layout.addWidget(self.welcome_recent_heading)

        # Recent files list widget
        self.welcome_recent_files_list = WelcomeRecentFilesList(self.user_data)
        self.welcome_recent_files_list.file_selected.connect(self._on_recent_file_selected)
        recent_layout.addWidget(self.welcome_recent_files_list)

        layout.addWidget(recent_container)
        layout.addSpacing(16)

        # Content browser section
        from immersion_app.gui.widgets.content_browser_grid import ContentBrowserGrid
        browser_container = QWidget()
        browser_layout = QVBoxLayout(browser_container)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        browser_layout.setSpacing(4)

        # Section heading
        self.welcome_browser_heading = QLabel("Library")
        self.welcome_browser_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        browser_layout.addWidget(self.welcome_browser_heading)

        # Content browser grid widget
        self.content_browser_grid = ContentBrowserGrid(
            self.content_browser_manager,
            self.preview_generator
        )
        self.content_browser_grid.content_selected.connect(self._on_browser_content_selected)
        browser_layout.addWidget(self.content_browser_grid, stretch=1)

        layout.addWidget(browser_container, stretch=2)
        layout.addSpacing(12)

        # Buttons
        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        self.welcome_open_button = QPushButton("Open Source")
        self.welcome_open_button.setFixedHeight(40)
        self.welcome_open_button.setMinimumWidth(140)
        self.welcome_open_button.clicked.connect(self._open_content_dialog)
        button_row.addWidget(self.welcome_open_button)

        self.welcome_queue_button = QPushButton("View Queue")
        self.welcome_queue_button.setFixedHeight(40)
        self.welcome_queue_button.setMinimumWidth(140)
        self.welcome_queue_button.clicked.connect(self._show_queue_dialog)
        button_row.addWidget(self.welcome_queue_button)

        wrapper = QWidget()
        wrapper.setLayout(button_row)
        layout.addWidget(wrapper, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(12)

        # Keyboard shortcuts hint
        self.welcome_shortcuts_label = QLabel("Ctrl+O to open")
        self.welcome_shortcuts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.welcome_shortcuts_label)

        layout.addSpacing(8)

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
        column_layout.setContentsMargins(8, 4, 8, 4)
        column_layout.setSpacing(0)

        # PDF scroll area
        self.pdf_label = PdfClickableLabelWidget()
        self.pdf_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.pdf_label.clicked.connect(self._on_pdf_click)
        self.pdf_label.hovered.connect(self._on_pdf_hover)
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
            {Theme.get_scrollbar_style()}
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
        self.pdf_status_bar.anki_status_clicked.connect(self._refresh_anki_status)
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

    def create_subtitle_generation_worker(self, video_path: str, model_size: str, language: str):
        return SubtitleGeneratorWorker(video_path, model_size, language)

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
            self.queue_dialog = QueueDialogWidget(self)
            self.queue_dialog.process_button.clicked.connect(self._process_queue_from_dialog)
        self.queue_dialog.refresh(entries)
        self.queue_dialog.show()
        self.queue_dialog.raise_()
        self.queue_dialog.activateWindow()

    def _on_page_completion_toggled(self, file_path: str, page: int, is_checked: bool):
        """Handle page completion toggle from shortcut panel."""
        if is_checked:
            # Mark this page and all previous pages complete
            for page_index in range(page + 1):
                self.completion_tracker.mark_page_complete(file_path, page_index)
        else:
            self.completion_tracker.unmark_page_complete(file_path, page)

    def _on_completion_changed_from_tracker(self, file_path: str, page: int, is_complete: bool):
        """Handle completion state changes from tracker (for feedback)."""
        if is_complete:
            # Show success toast
            self.card_feedback_toast.show_feedback(
                title="Page marked complete!",
                body=f"Page {page + 1} completed on {datetime.now().strftime('%b %d, %Y')}",
                variant="added"
            )

    def _update_shortcut_panel_visibility(self, mode: WorkspaceMode):
        """Show/hide shortcut panel based on mode."""
        if mode in (WorkspaceMode.PDF, WorkspaceMode.VIDEO):
            self.shortcut_panel.show()
            self.shortcut_panel.position_on_parent()
        else:
            self.shortcut_panel.hide()

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
        if self.translation_service.is_mode_available("online") and self.translation_mode != "offline":
            self.translation_mode = "online"
        elif self.translation_service.is_mode_available("offline"):
            self.translation_mode = "offline"
        self.translation_service.set_mode(self.translation_mode)
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
        if self.translation_mode == "online":
            if not self.translation_service.is_mode_available("offline"):
                logger.warning("Cannot switch to offline mode: backend not available")
                self._set_status("Offline translation backend is not installed.")
                return
            self.translation_mode = "offline"
        else:
            if not self.translation_service.is_mode_available("online"):
                logger.warning("Cannot switch to online mode: backend not available")
                self._set_status("Online translation backend is not installed.")
                return
            self.translation_mode = "online"
        self.translation_service.set_mode(self.translation_mode)
        self._update_translation_status_label()

    def _set_appearance_mode(self, mode: str):
        self.appearance_manager.set_mode(mode)

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
        self.mining_controller.set_languages(self.learning_language, self.native_language)
        self.user_data["preferences"]["learning_language"] = self.learning_language
        save_user_data(self.user_data)
        self._set_status(f"Learning language: {get_language_label(self.learning_language)}")

    def _set_native_language(self, code):
        self.native_language = normalize_language_code(code, DEFAULT_NATIVE_LANGUAGE)
        self.mining_controller.set_languages(self.learning_language, self.native_language)
        self.user_data["preferences"]["native_language"] = self.native_language
        save_user_data(self.user_data)
        self._set_status(f"Native language: {get_language_label(self.native_language)}")

    def _reset_translation_cache(self):
        self.translation_service.clear_cache()

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
        if hasattr(self, "mining_controller"):
            self.mining_controller.request_translation(text)
            return
        self._start_translation_request(text, visible=True)

    def _prefetch_translations(self, texts):
        if hasattr(self, "mining_controller"):
            self.mining_controller.prefetch_translations(list(texts))
            return
        if not texts:
            return
        texts_to_fetch = []
        for text in texts:
            if not text:
                continue
            key = self._translation_cache_key(text)
            if key not in self.translation_cache and key not in self._translation_requests_by_key:
                texts_to_fetch.append(text)
        if not texts_to_fetch:
            return
        if self.translation_mode == "online":
            self._prefetch_translations_batch(texts_to_fetch)
        else:
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
        if hasattr(self, "mining_controller"):
            self.mining_controller.submit_manual_word(self.word_value.text())
            return
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

        if had_pdf_selection and self.pdf_service.doc and self.mode_manager.current_mode == WorkspaceMode.PDF:
            self.pdf_controller.render_current_page()
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
        return self.pdf_controller.selection_anchor_rect()

    def _update_command_bar_stats(self):
        """Update the stats chip in the command bar."""
        today_count = self.anki_analytics.today_count()
        total_count = self.anki_analytics.total_vocabulary_count()
        self.command_bar.set_stats(today_count, total_count)

    def _on_anki_analytics_changed(self, today_count: int, total_count: int):
        """Refresh UI when Anki analytics change."""
        self.analytics_vocabulary = set(self.anki_analytics.vocabulary_seen)
        self.command_bar.set_stats(today_count, total_count)
        self._refresh_word_highlights()

    def _on_video_loaded_for_usage(self, subtitle_count: int):
        """Handle video loaded signal for usage tracking."""
        # Video service doesn't have a video_loaded signal, but we can track via subtitle loading
        # When subtitles are loaded, use the current video path if available
        if hasattr(self, 'current_video_path') and self.current_video_path:
            self.usage_tracker.on_video_loaded(self.current_video_path)

    def _on_usage_tracking_status_changed(self, is_active: bool):
        """Update status bars when usage tracking active status changes."""
        if hasattr(self, 'pdf_status_bar'):
            self.pdf_status_bar.set_usage_tracking_active(is_active)
        if hasattr(self, 'transport_bar'):
            self.transport_bar.set_usage_tracking_active(is_active)

    def _jump_to_page(self, page_number: int):
        if hasattr(self, "pdf_controller"):
            self.pdf_controller.jump_to_page(page_number)
            return
        if not self.doc or not (1 <= page_number <= self.doc.page_count):
            return
        self.current_page_index = page_number - 1
        self.selection.pdf.highlight_bboxes = []
        self._clear_selection_state()
        self._render_current_page()
        self._reset_pdf_scroll_position()
        self._persist_session()

    def _reset_pdf_scroll_position(self):
        if not hasattr(self, "scroll_area") or self.scroll_area is None:
            return
        self.scroll_area.verticalScrollBar().setValue(0)

    def _replay_subtitle(self):
        self.video_controller.replay_subtitle()

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
        self.anki_service.refresh_connection()

    def _on_anki_status_check_started(self, request_id):
        logger.info(f"Refreshing Anki connection state (request_id={request_id})")
        self.anki_status_label.setText("Anki: checking...")
        if hasattr(self, "pdf_status_bar"):
            self.pdf_status_bar.set_anki_status(connected=False, checking=True)

    def _on_anki_connection_changed(self, connected):
        self.is_anki_connected = connected
        self.anki_status_label.setText("Anki: connected" if connected else "Anki: not connected")
        self.health_label.setText(
            f"Anki: {'ready' if connected else 'not connected'}\nTranslation backend: {self.translation_mode}"
        )
        if hasattr(self, "pdf_status_bar"):
            self.pdf_status_bar.set_anki_status(connected=connected, checking=False)

    def _on_anki_vocabulary_loaded(self, words):
        save_snapshot(words)
        self.anki_analytics.set_snapshot_words(words)
        self.analytics_vocabulary = set(self.anki_analytics.vocabulary_seen)
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
        self.anki_analytics.record_successful_card_add(word_text)
        self.analytics_vocabulary = set(self.anki_analytics.vocabulary_seen)
        logger.info(
            f"Recorded card add for '{word_text}' "
            f"(total cards: {self.anki_analytics.total_cards_added()}, vocabulary: {len(self.analytics_vocabulary)} words)"
        )

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
        if hasattr(self, "mining_controller"):
            self.mining_controller.add_now()
            return
        if not self.selection.word or not self.selection.translation:
            return
        if not getattr(self, "is_anki_connected", False):
            self._queue_current_selection_for_later("AnkiConnect is not available")
            return
        try:
            note_sentence = self._build_note_sentence()
            note_id = add_anki_card(note_sentence, self.selection.word, self.selection.translation)
            self._record_successful_card_add(self.selection.word)
            self._show_card_feedback("Added to Anki", note_sentence, "added", note_id=note_id)
            self._close_popover()
        except Exception as exc:
            if isinstance(exc, ConnectionError):
                self._queue_current_selection_for_later(str(exc))
                return
            QMessageBox.critical(self, "Anki Add Failed", str(exc))

    def _add_to_queue(self):
        if hasattr(self, "mining_controller"):
            self.mining_controller.add_to_queue()
            return
        if not self.selection.word or not self.selection.translation:
            return
        try:
            payload = self._queue_payload()
            append_queue_entry(payload)
            self._refresh_queue_summary()
            self._show_card_feedback("Saved to queue", payload["sentence"], "queued")
        except Exception as exc:
            QMessageBox.critical(self, "Queue Write Failed", str(exc))

    def _process_queue(self):
        if hasattr(self, "mining_controller"):
            self.mining_controller.process_queue()
            return
        entries = load_queue_entries()
        if not entries:
            QMessageBox.information(self, "Queue Empty", "No queued cards found.")
            return
        if not getattr(self, "is_anki_connected", False):
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
        self.workspace_controller.open_content_dialog()

    def _close_current_file(self):
        self.workspace_controller.close_current_file()

    def _load_pdf(self, path, initial_page_index=0):
        if hasattr(self, "pdf_controller"):
            self.pdf_controller.load_pdf(path, initial_page_index=initial_page_index)
            self.current_pdf_path = self.pdf_controller.current_pdf_path
            self.current_page_index = self.pdf_controller.current_page_index
            self.doc = self.pdf_service.doc
            return
        self.doc = fitz.open(path)
        self.current_pdf_path = path
        self.current_page_index = max(0, min(initial_page_index, self.doc.page_count - 1))
        self.current_source_name = Path(path).name
        self.current_source_location = f"Page {self.current_page_index + 1}"
        self._clear_selection_state()
        QTimer.singleShot(0, self._fit_width)
        QTimer.singleShot(0, self._reset_pdf_scroll_position)
        self._update_source_summary()
        self._persist_session()
        self._set_status(f"Opened PDF: {Path(path).name}")
        self.command_bar.set_title(Path(path).name, f"{self.doc.page_count} pages")
        self.command_bar.set_file_loaded(True)
        self.command_bar.set_page_info(self.current_page_index + 1, self.doc.page_count)
        self._update_command_bar_stats()
        self.mode_manager.set_pdf_loaded(True)
        self.mode_manager.set_mode(WorkspaceMode.PDF, force=True)
        from immersion_app.core.recent_files import add_recent_file
        add_recent_file(self.user_data, str(self.current_pdf_path), "pdf", {"page_index": self.current_page_index})
        save_user_data(self.user_data)

    def _render_current_page(self):
        if hasattr(self, "pdf_controller"):
            self.pdf_controller.render_current_page()
            self.page_words = self.pdf_controller.page_words
            self.page_word_order = self.pdf_controller.page_word_order
            self.page_word_index = self.pdf_controller.page_word_index
            self.page_line_words = self.pdf_controller.page_line_words
            self.current_page_index = self.pdf_controller.current_page_index
            self.zoom_factor = self.pdf_controller.zoom_factor
            return
        if not self.doc:
            return
        page = self.doc.load_page(self.current_page_index)
        matrix = fitz.Matrix(self.zoom_factor, self.zoom_factor)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
        if self.appearance_manager.current_mode == AppearanceMode.DARK:
            image.invertPixels()
        painter = QPainter(image)
        painter.end()
        pixmap = QPixmap.fromImage(image)
        self.pdf_label.setPixmap(pixmap)
        self.pdf_label.resize(pixmap.size())
        self.page_words = page.get_text("words")
        self.page_word_order = sorted(self.page_words, key=lambda w: (int(w[5]), int(w[6]), int(w[7]), float(w[1]), float(w[0])))
        self.page_word_index = {self._word_key(word): idx for idx, word in enumerate(self.page_word_order)}
        self.page_line_words = self._build_line_index(self.page_words)
        self.current_source_location = f"Page {self.current_page_index + 1}"
        self._update_source_summary()
        self.command_bar.set_page_info(self.current_page_index + 1, self.doc.page_count)
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
        self.pdf_controller.click_at(point, modifiers)

    def _on_pdf_hover(self, point, modifiers):
        self.pdf_controller.hover_at(point, modifiers)

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
        if hasattr(self, "pdf_controller"):
            self.pdf_controller.prev_page()
            return
        if not self.doc or self.current_page_index <= 0:
            return
        self.current_page_index -= 1
        self.selection.pdf.highlight_bboxes = []
        self._clear_selection_state()
        self._render_current_page()
        self._reset_pdf_scroll_position()
        self._persist_session()

    def _next_page(self):
        if hasattr(self, "pdf_controller"):
            self.pdf_controller.next_page()
            return
        if not self.doc or self.current_page_index >= self.doc.page_count - 1:
            return
        self.current_page_index += 1
        self.selection.pdf.highlight_bboxes = []
        self._clear_selection_state()
        self._render_current_page()
        self._reset_pdf_scroll_position()
        self._persist_session()

    def _zoom_in(self):
        if hasattr(self, "pdf_controller"):
            self.pdf_controller.zoom_in()
            return
        if self.doc:
            self.zoom_factor = min(4.0, self.zoom_factor + 0.25)
            self._render_current_page()

    def _zoom_out(self):
        if hasattr(self, "pdf_controller"):
            self.pdf_controller.zoom_out()
            return
        if self.doc:
            self.zoom_factor = max(0.5, self.zoom_factor - 0.25)
            self._render_current_page()

    def _reset_zoom(self):
        if hasattr(self, "pdf_controller"):
            self.pdf_controller.reset_zoom()
            return
        if self.doc:
            self.zoom_factor = 2.0
            self._render_current_page()

    def _fit_width(self):
        if hasattr(self, "pdf_controller"):
            self.pdf_controller.fit_width()
            return
        if not self.doc:
            return
        page = self.doc.load_page(self.current_page_index)
        reading_column = self.scroll_area.parent()
        available = max(200, reading_column.width() - 72)
        self.zoom_factor = max(0.5, min(4.0, (available / page.rect.width) - 0.25))
        self._render_current_page()



    def _open_subtitle_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load subtitles", "", "SRT Files (*.srt)")
        if not path:
            return
        self._load_subtitles(path)

    def _load_video(self, path, restore_position_ms=0):
        self.video_controller.load_video(path, restore_position_ms=restore_position_ms)
        self.current_video_path = self.video_controller.current_video_path

    def _load_subtitles(self, srt_path):
        self.video_controller.load_subtitles(srt_path)
        self.subtitle_parser = self.video_service.subtitle_parser
        self.current_srt_path = self.video_service.current_srt_path

    def _generate_subtitles_interactive(self):
        self.video_controller.generate_subtitles_interactive()

    def _on_subtitle_generation_finished(self, dialog, srt_path):
        dialog.status_label.setText("Finished")
        self._load_subtitles(srt_path)
        self._set_status(f"Generated subtitles: {Path(srt_path).name}")

    def _on_subtitle_click(self, word, token_index, modifiers):
        if hasattr(self, "video_controller"):
            self.video_controller.on_subtitle_click(token_index, modifiers)
            return
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
        if hasattr(self, "video_controller"):
            self.video_controller.on_position_changed(position)
            return
        if not self._is_slider_dragging:
            self.transport_bar.set_position(position)
        duration = self.media_player.duration()
        self.transport_bar.set_time(position, duration)
        self.current_source_location = self._fmt_ms(position)
        self.subtitle_offset_label.setText(f"Subtitle Offset: {self.subtitle_offset_ms / 1000.0:+.2f}s")
        self._refresh_subtitle_for_position(position)
        self._update_source_summary()

    def _refresh_subtitle_for_position(self, position):
        if hasattr(self, "video_controller"):
            self.video_controller.refresh_subtitle_for_position(position)
            self.current_subtitle = self.video_controller.current_subtitle
            return
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
        self.video_controller.toggle_play_pause()

    def _seek_relative(self, delta_ms):
        current = self.media_player.position()
        target = max(0, min(self.media_player.duration(), current + delta_ms))
        self.media_player.setPosition(target)

    def _adjust_subtitle_offset(self, delta_ms):
        self.video_service.set_offset(self.video_service.subtitle_offset_ms + delta_ms)
        self.subtitle_offset_ms = self.video_service.subtitle_offset_ms
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
                "subtitle_offset_ms": int(self.video_service.subtitle_offset_ms),
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
        self.workspace_controller.restore_last_session()

    def closeEvent(self, event):
        # Finalize usage time session before closing
        if hasattr(self, 'usage_tracker'):
            self.usage_tracker.finalize_current_session()
        self._persist_session()
        super().closeEvent(event)
