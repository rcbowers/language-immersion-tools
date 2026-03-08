#!/usr/bin/env python3
"""Shared sentence miner window components."""

import json
import os
import re
import socket
import subprocess
from abc import abstractmethod
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from translation_backends import OnlineTranslationBackend, OfflineTranslationBackend
from spanish_sentence_miner import (
    INPUT_FILE,
    PROCESSED_FILE,
    add_anki_card,
    append_to_processed_file,
    parse_input_file,
    rewrite_input_file,
    test_anki_connection,
)

ANKI_PATH = r"C:\Program Files\Anki\anki.exe"


class TranslateSignals(QObject):
    finished = Signal(int, str, str)
    failed = Signal(int, str)


class TranslateTask(QRunnable):
    def __init__(self, request_id, text, src_lang, dest_lang, backend):
        super().__init__()
        self.signals = TranslateSignals()
        self.request_id = request_id
        self.text = text
        self.src_lang = src_lang
        self.dest_lang = dest_lang
        self.backend = backend

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
    finished = Signal(int, bool, bool)


class AnkiStatusTask(QRunnable):
    def __init__(self, request_id, initial):
        super().__init__()
        self.request_id = request_id
        self.initial = initial
        self.signals = AnkiStatusSignals()

    def run(self):
        connected = test_anki_connection()
        try:
            self.signals.finished.emit(self.request_id, connected, self.initial)
        except RuntimeError:
            return


class AbstractSentenceMinerWindow(QMainWindow):
    def __init__(self, title):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1500, 950)

        self.translation_cache = {}
        self.thread_pool = QThreadPool.globalInstance()
        self.current_request_id = 0
        self.anki_check_request_id = 0

        self.selected_word = ""
        self.selected_sentence = ""
        self.selected_translation = ""
        self.is_anki_connected = False
        self.sentence_counts = {}
        self.anki_process = None

        self.ui_scale = 1.0
        self.min_ui_scale = 0.8
        self.max_ui_scale = 1.8
        self.base_font = QApplication.font()

        self.user_data_path = Path(INPUT_FILE).resolve().with_name("sentence_miner_user_data.json")
        self.user_data = self._get_default_user_data()
        self.analytics_vocabulary = set()
        self._load_user_data()

        self.translation_mode = "online"
        self.internet_available = True
        self.translation_status_label = None
        self.mode_indicator_label = None

        self.main_splitter = None
        self.right_panel = None

        self._build_base_ui()
        self._build_mode_toolbar()
        self._apply_ui_scale()
        self._determine_translation_mode()
        self._refresh_anki_status(initial=True)
        self._restore_common_preferences()
        self._restore_session_state()

    def _build_base_ui(self):
        self.main_splitter = QSplitter()
        self.main_splitter.setOrientation(Qt.Orientation.Horizontal)

        viewer_panel = self._build_viewer_panel()
        self.right_panel = self._build_right_panel()

        self.main_splitter.addWidget(viewer_panel)
        self.main_splitter.addWidget(self.right_panel)
        self.main_splitter.setSizes([1100, 380])

        self.setCentralWidget(self.main_splitter)

        status = QStatusBar()
        self.setStatusBar(status)
        self.translation_status_label = QLabel("Translation: checking...")
        status.addPermanentWidget(self.translation_status_label)
        self.anki_status_label = QLabel("Anki: checking...")
        status.addPermanentWidget(self.anki_status_label)

    @abstractmethod
    def _build_viewer_panel(self):
        raise NotImplementedError

    @abstractmethod
    def _build_mode_toolbar(self):
        raise NotImplementedError

    @abstractmethod
    def _restore_session_state(self):
        raise NotImplementedError

    @abstractmethod
    def _persist_last_session(self):
        raise NotImplementedError

    @abstractmethod
    def _clear_viewer_state(self):
        raise NotImplementedError

    def _build_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        selection_group = QGroupBox("Selection")
        selection_form = QFormLayout(selection_group)

        self.word_value = QLabel("(none)")
        self.word_value.setWordWrap(True)
        selection_form.addRow("Word:", self.word_value)

        self.sentence_value = QTextEdit()
        self.sentence_value.setReadOnly(True)
        self.sentence_value.setFixedHeight(120)
        selection_form.addRow("Context:", self.sentence_value)

        self.translation_value = QTextEdit()
        self.translation_value.setReadOnly(True)
        self.translation_value.setFixedHeight(100)
        selection_form.addRow("Translation:", self.translation_value)

        layout.addWidget(selection_group)

        actions_group = QGroupBox("Card Actions")
        actions_layout = QVBoxLayout(actions_group)

        self.add_now_button = QPushButton("Add Now")
        self.add_now_button.setShortcut(QKeySequence("Ctrl+Return"))
        self.add_now_button.clicked.connect(self._add_now)
        actions_layout.addWidget(self.add_now_button)

        self.add_queue_button = QPushButton("Add to Queue")
        self.add_queue_button.setShortcut(QKeySequence("Ctrl+Shift+Return"))
        self.add_queue_button.clicked.connect(self._add_to_queue)
        actions_layout.addWidget(self.add_queue_button)

        self.process_queue_button = QPushButton("Process Queue")
        self.process_queue_button.clicked.connect(self._process_queue)
        actions_layout.addWidget(self.process_queue_button)

        layout.addWidget(actions_group)

        self.queue_info = QLabel(f"Queue file: {INPUT_FILE}")
        self.queue_info.setWordWrap(True)
        layout.addWidget(self.queue_info)

        self.mode_indicator_label = QLabel("Translation Mode: Checking...")
        self.mode_indicator_label.setWordWrap(True)
        font = self.mode_indicator_label.font()
        font.setBold(True)
        self.mode_indicator_label.setFont(font)
        layout.addWidget(self.mode_indicator_label)

        layout.addStretch(1)
        self._update_action_buttons()

        return panel

    def _set_status(self, message, timeout_ms=4000):
        self.statusBar().showMessage(message, timeout_ms)

    def _add_menu_action(self, menu, text, slot, shortcuts=None):
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcuts:
            if isinstance(shortcuts, (list, tuple)):
                action.setShortcuts([QKeySequence(value) for value in shortcuts])
            else:
                action.setShortcut(QKeySequence(shortcuts))
            self.addAction(action)
        menu.addAction(action)
        return action

    def _add_toolbar_menu_button(self, toolbar, title, menu):
        button = QToolButton(toolbar)
        button.setText(title)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(menu)
        toolbar.addWidget(button)
        return button

    def _build_common_toolbar_menus(self, toolbar):
        window_menu = QMenu("Window", self)
        self._add_menu_action(
            window_menu,
            "Zoom GUI in",
            self._increase_ui_scale,
            shortcuts=["Ctrl++", "Ctrl+="],
        )
        self._add_menu_action(window_menu, "Zoom GUI out", self._decrease_ui_scale, shortcuts="Ctrl+-")
        self._add_toolbar_menu_button(toolbar, "Window", window_menu)

        anki_menu = QMenu("Anki", self)
        self._add_menu_action(anki_menu, "Start Anki", self._start_anki)
        self._add_menu_action(anki_menu, "Check Anki", self._refresh_anki_status)
        self._add_toolbar_menu_button(toolbar, "Anki", anki_menu)

        translation_menu = QMenu("Translation", self)
        self._add_menu_action(translation_menu, "Translation mode", self._toggle_translation_mode)
        self._add_toolbar_menu_button(toolbar, "Translation", translation_menu)

    def _apply_ui_scale(self):
        scaled_font = QFont(self.base_font)
        current_size = scaled_font.pointSizeF()
        if current_size <= 0:
            current_size = 10.0
        scaled_font.setPointSizeF(current_size * self.ui_scale)
        QApplication.instance().setFont(scaled_font)

    def _increase_ui_scale(self):
        self.ui_scale = min(self.max_ui_scale, self.ui_scale + 0.1)
        self._apply_ui_scale()
        self._persist_common_preferences()
        self._set_status(f"UI scale: {int(self.ui_scale * 100)}%", 1500)

    def _decrease_ui_scale(self):
        self.ui_scale = max(self.min_ui_scale, self.ui_scale - 0.1)
        self._apply_ui_scale()
        self._persist_common_preferences()
        self._set_status(f"UI scale: {int(self.ui_scale * 100)}%", 1500)

    def _clear_selection_state(self):
        self.selected_word = ""
        self.selected_sentence = ""
        self.selected_translation = ""
        self._update_selection_panel()
        self._update_action_buttons()

    def _clean_word(self, value):
        start = 0
        end = len(value)

        while start < end and not (value[start].isalpha() or value[start].isdigit() or value[start] == "_"):
            start += 1

        while end > start and not (value[end - 1].isalpha() or value[end - 1].isdigit() or value[end - 1] == "_"):
            end -= 1

        return value[start:end].strip()

    def _request_translation(self, text):
        if not text:
            return

        key = ("es", "en", text)
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

        task = TranslateTask(request_id, text, "es", "en", backend)
        task.signals.finished.connect(self._on_translation_done)
        task.signals.failed.connect(self._on_translation_failed)
        self.thread_pool.start(task)

    def _is_garbage_translation(self, translated_text):
        if not translated_text or len(translated_text.strip()) < 2:
            return True

        words = translated_text.split()
        if len(words) > 20:
            repeated_phrases = [
                "The\nThe",
                "to the",
                "of the",
                "in the",
            ]
            for phrase in repeated_phrases:
                repeats = translated_text.count(phrase)
                if repeats > 3:
                    return True
        return False

    def _on_translation_done(self, request_id, source_text, translated_text):
        if request_id != self.current_request_id:
            return

        if self._is_garbage_translation(translated_text):
            self._on_translation_failed(request_id, "Google Translate returned invalid response")
            return

        key = ("es", "en", source_text)
        self.translation_cache[key] = translated_text
        self.selected_translation = translated_text
        self._update_selection_panel()
        self._update_action_buttons()
        self._update_translation_status_label()

    def _on_translation_failed(self, request_id, error_message):
        if request_id != self.current_request_id:
            return

        if self.translation_mode == "online":
            offline_backend = OfflineTranslationBackend()
            if offline_backend.is_available():
                self._set_status("Online translation failed, trying offline mode...", 3000)
                self.translation_mode = "offline"
                self._update_translation_status_label()
                self._request_translation(self.selected_word)
                return
        elif self.translation_mode == "offline":
            online_backend = OnlineTranslationBackend()
            if online_backend.is_available() and self._check_internet_connection():
                self._set_status("Offline translation failed, trying online mode...", 3000)
                self.translation_mode = "online"
                self._update_translation_status_label()
                self._request_translation(self.selected_word)
                return

        self.selected_translation = f"Translation error: {error_message}"
        self._update_selection_panel()
        self._update_action_buttons()
        self._set_status(f"Translation failed: {error_message}", 4000)

    def _update_selection_panel(self):
        self.word_value.setText(self.selected_word or "(none)")
        self.sentence_value.setText(self.selected_sentence)
        self.translation_value.setText(self.selected_translation)

    def _update_action_buttons(self):
        has_selection = bool(self.selected_word and self.selected_sentence)
        has_translation = bool(self.selected_translation and not self.selected_translation.startswith("Translation error:"))
        self.add_now_button.setEnabled(has_selection and has_translation)
        self.add_queue_button.setEnabled(has_selection and has_translation)

    def _refresh_anki_status(self, initial=False):
        self.anki_check_request_id += 1
        request_id = self.anki_check_request_id
        self.anki_status_label.setText("Anki: checking...")

        task = AnkiStatusTask(request_id, initial)
        task.signals.finished.connect(self._on_anki_status_checked)
        self.thread_pool.start(task)

    def _on_anki_status_checked(self, request_id, connected, initial):
        if request_id != self.anki_check_request_id:
            return
        self.is_anki_connected = connected
        if connected:
            self.anki_status_label.setText("Anki: connected")
            self._set_status("Connected to Anki", 2000 if not initial else 1000)
        else:
            self.anki_status_label.setText("Anki: not connected")
            if not initial:
                self._set_status("Could not reach AnkiConnect", 3000)

    def _check_internet_connection(self):
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return True
        except OSError:
            return False

    def _determine_translation_mode(self):
        self.internet_available = self._check_internet_connection()
        if self.internet_available and OnlineTranslationBackend().is_available():
            self.translation_mode = "online"
        elif OfflineTranslationBackend().is_available():
            self.translation_mode = "offline"
        else:
            self.translation_mode = "online"
        self._update_translation_status_label()

    def _update_translation_status_label(self, message=None):
        if message:
            if self.translation_status_label:
                self.translation_status_label.setText(f"Translation: {message}")
                self.translation_status_label.setStyleSheet("color: orange;")
            if self.mode_indicator_label:
                self.mode_indicator_label.setText(f"Translation Mode: {message}")
                self.mode_indicator_label.setStyleSheet("color: orange;")
        elif self.translation_mode == "online":
            self.translation_status_label.setText("Translation: Online")
            self.translation_status_label.setStyleSheet("color: green;")
            self.mode_indicator_label.setText("Translation Mode: ONLINE")
            self.mode_indicator_label.setStyleSheet("color: green;")
        elif self.translation_mode == "offline":
            self.translation_status_label.setText("Translation: Offline")
            self.translation_status_label.setStyleSheet("color: blue;")
            self.mode_indicator_label.setText("Translation Mode: OFFLINE")
            self.mode_indicator_label.setStyleSheet("color: blue;")
        else:
            self.translation_status_label.setText("Translation: Error")
            self.translation_status_label.setStyleSheet("color: red;")
            self.mode_indicator_label.setText("Translation Mode: ERROR")
            self.mode_indicator_label.setStyleSheet("color: red;")

    def _toggle_translation_mode(self):
        if self.translation_mode == "online":
            if not OfflineTranslationBackend().is_available():
                QMessageBox.information(self, "Offline Translation Not Available", "Install argostranslate for offline mode.")
                return
            self.translation_mode = "offline"
            self._set_status("Switched to offline translation mode", 2000)
        else:
            if not OnlineTranslationBackend().is_available():
                QMessageBox.warning(self, "Online Translation Not Available", "Install googletrans for online mode.")
                return
            self.translation_mode = "online"
            self._set_status("Switched to online translation mode", 2000)
        self._update_translation_status_label()

    def _start_anki(self):
        if self._is_anki_running_process():
            self._set_status("Anki already appears to be running")
            QTimer.singleShot(1500, self._refresh_anki_status)
            return

        if not os.path.exists(ANKI_PATH):
            QMessageBox.warning(self, "Anki Not Found", f"Anki executable not found at:\n{ANKI_PATH}")
            return

        try:
            self.anki_process = subprocess.Popen([ANKI_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            QMessageBox.critical(self, "Start Anki Failed", str(exc))
            return

        self._set_status("Anki started, checking connection...")
        QTimer.singleShot(3500, self._refresh_anki_status)

    def _is_anki_running_process(self):
        try:
            import psutil
        except ImportError:
            return False

        for proc in psutil.process_iter(["name"]):
            name = proc.info.get("name")
            if name and "anki" in name.lower():
                return True
        return False

    def _build_note_sentence(self):
        sentence = self.selected_sentence or self.selected_word
        if sentence in self.sentence_counts:
            self.sentence_counts[sentence] += 1
            return f"{sentence} ({self.sentence_counts[sentence]})"
        self.sentence_counts[sentence] = 1
        return sentence

    def _add_now(self):
        if not self.selected_word or not self.selected_translation:
            return
        if not self.is_anki_connected:
            QMessageBox.warning(self, "Anki Not Connected", "AnkiConnect is not available. Click Check Anki and retry.")
            return

        sentence_for_note = self._build_note_sentence()
        try:
            note_id = add_anki_card(sentence_for_note, self.selected_word, self.selected_translation)
            self._record_successful_card_add(self.selected_word, self.selected_sentence or self.selected_word)
            self._set_status(f"Added card to Anki (Note ID: {note_id})")
        except Exception as exc:
            QMessageBox.critical(self, "Anki Add Failed", str(exc))

    def _add_to_queue(self):
        if not self.selected_word or not self.selected_translation:
            return

        sentence = self.selected_sentence or self.selected_word
        try:
            self._append_queue_entry(sentence, self.selected_word, self.selected_translation)
            self._set_status(f"Queued word '{self.selected_word}'")
        except Exception as exc:
            QMessageBox.critical(self, "Queue Write Failed", str(exc))

    def _append_queue_entry(self, sentence, target_word, translation):
        queue_path = Path(INPUT_FILE)
        needs_newline = False

        if queue_path.exists():
            existing = queue_path.read_text(encoding="utf-8")
            if existing and not existing.endswith("\n"):
                needs_newline = True

        with open(INPUT_FILE, "a", encoding="utf-8") as handle:
            if needs_newline:
                handle.write("\n")
            if queue_path.exists() and queue_path.stat().st_size > 0:
                handle.write("\n")
            handle.write(f"{sentence}\n{target_word}\n{translation}\n")

    def _process_queue(self):
        if not Path(INPUT_FILE).exists():
            QMessageBox.information(self, "Queue Empty", f"{INPUT_FILE} does not exist.")
            return

        try:
            entries = parse_input_file(INPUT_FILE)
        except Exception as exc:
            QMessageBox.critical(self, "Queue Parse Error", str(exc))
            return

        if not entries:
            QMessageBox.information(self, "Queue Empty", f"No valid entries found in {INPUT_FILE}.")
            return

        if not self.is_anki_connected:
            QMessageBox.warning(self, "Anki Not Connected", "AnkiConnect is not available. Click Check Anki and retry.")
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
                self._record_successful_card_add(entry["word"], entry["sentence"])
            except Exception:
                failed_entries.append(entry)

        if successful_entries:
            append_to_processed_file(successful_entries)
        rewrite_input_file(failed_entries)

        QMessageBox.information(
            self,
            "Queue Processed",
            (
                f"Added: {len(successful_entries)}\n"
                f"Failed: {len(failed_entries)}\n"
                f"Log: {PROCESSED_FILE}"
            ),
        )
        self._set_status("Queue processing complete")

    def _get_default_user_data(self):
        return {
            "version": 1,
            "mode": "pdf",
            "preferences": {
                "preferred_mode": None,
                "video_playback_speed": 1.0,
                "ui_scale": 1.0,
            },
            "last_session": {
                "pdf_path": "",
                "page_index": 0,
                "video_path": "",
                "video_position_ms": 0,
                "srt_path": "",
            },
            "analytics": {
                "cards_added_total": 0,
                "total_unique_vocabulary": 0,
                "total_words_read": 0,
                "vocabulary_seen": [],
            },
        }

    def _load_user_data(self):
        self.user_data = self._get_default_user_data()

        if self.user_data_path.exists():
            try:
                loaded = json.loads(self.user_data_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.user_data.update(loaded)
            except Exception:
                pass

        preferences = self.user_data.get("preferences")
        if not isinstance(preferences, dict):
            preferences = {}

        last_session = self.user_data.get("last_session")
        if not isinstance(last_session, dict):
            last_session = {}

        analytics = self.user_data.get("analytics")
        if not isinstance(analytics, dict):
            analytics = {}

        self.user_data["preferences"] = {
            "preferred_mode": preferences.get("preferred_mode"),
            "video_playback_speed": float(preferences.get("video_playback_speed") or 1.0),
            "ui_scale": float(preferences.get("ui_scale") or 1.0),
        }

        self.user_data["last_session"] = {
            "pdf_path": str(last_session.get("pdf_path") or ""),
            "page_index": int(last_session.get("page_index") or 0),
            "video_path": str(last_session.get("video_path") or ""),
            "video_position_ms": int(last_session.get("video_position_ms") or 0),
            "srt_path": str(last_session.get("srt_path") or ""),
        }

        raw_vocab = analytics.get("vocabulary_seen", [])
        if not isinstance(raw_vocab, list):
            raw_vocab = []
        self.analytics_vocabulary = {str(item) for item in raw_vocab if str(item).strip()}

        self.user_data["analytics"] = {
            "cards_added_total": int(analytics.get("cards_added_total") or 0),
            "total_unique_vocabulary": len(self.analytics_vocabulary),
            "total_words_read": int(analytics.get("total_words_read") or 0),
            "vocabulary_seen": sorted(self.analytics_vocabulary),
        }

    def _save_user_data(self):
        self.user_data["analytics"]["total_unique_vocabulary"] = len(self.analytics_vocabulary)
        self.user_data["analytics"]["vocabulary_seen"] = sorted(self.analytics_vocabulary)
        temp_path = self.user_data_path.with_suffix(".tmp")
        payload = json.dumps(self.user_data, ensure_ascii=False, indent=2)
        temp_path.write_text(payload, encoding="utf-8")
        os.replace(temp_path, self.user_data_path)

    def _restore_common_preferences(self):
        prefs = self.user_data.get("preferences", {})
        self.ui_scale = max(self.min_ui_scale, min(self.max_ui_scale, float(prefs.get("ui_scale", 1.0))))
        self._apply_ui_scale()

    def _persist_common_preferences(self):
        self.user_data.setdefault("preferences", {})["ui_scale"] = self.ui_scale
        self._save_user_data()

    def _count_words(self, text):
        return len(re.findall(r"\b\w+\b", text or "", flags=re.UNICODE))

    def _extract_vocab_tokens(self, text):
        return {token.lower() for token in re.findall(r"\b\w+\b", text or "", flags=re.UNICODE)}

    def _record_successful_card_add(self, word_text, context_text):
        analytics = self.user_data["analytics"]
        analytics["cards_added_total"] += 1
        analytics["total_words_read"] += self._count_words(context_text)
        self.analytics_vocabulary.update(self._extract_vocab_tokens(word_text))
        analytics["total_unique_vocabulary"] = len(self.analytics_vocabulary)
        analytics["vocabulary_seen"] = sorted(self.analytics_vocabulary)
        self._save_user_data()

    def closeEvent(self, event):
        try:
            self._persist_last_session()
            self._persist_common_preferences()
        except Exception:
            pass
        super().closeEvent(event)
