#!/usr/bin/env python3
"""
PDF Sentence Miner GUI
PySide6 + PyMuPDF application for click-to-translate word mining from PDFs.
"""

import os
import re
import subprocess
import sys
import asyncio
import inspect
import json
from pathlib import Path

import fitz
from googletrans import Translator
from PySide6.QtCore import QObject, QPoint, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QImage, QIntValidator, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from spanish_sentence_miner import (
    INPUT_FILE,
    PROCESSED_FILE,
    add_anki_card,
    append_to_processed_file,
    parse_input_file,
    rewrite_input_file,
    test_anki_connection,
)

# Optional automatic Anki startup path.
ANKI_PATH = r"C:\Program Files\Anki\anki.exe"


class ClickablePdfLabel(QLabel):
    clicked = Signal(QPoint, object)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(event.position().toPoint(), event.modifiers())
        super().mousePressEvent(event)


class TranslateSignals(QObject):
    finished = Signal(int, str, str)
    failed = Signal(int, str)


class TranslateTask(QRunnable):
    def __init__(self, request_id, text, src_lang, dest_lang):
        super().__init__()
        self.signals = TranslateSignals()
        self.request_id = request_id
        self.text = text
        self.src_lang = src_lang
        self.dest_lang = dest_lang

    def run(self):
        try:
            translated_text = self._translate_text()
            self.signals.finished.emit(self.request_id, self.text, translated_text)
        except Exception as exc:
            self.signals.failed.emit(self.request_id, str(exc))

    async def _translate_async(self):
        async with Translator() as translator:
            result = await translator.translate(self.text, src=self.src_lang, dest=self.dest_lang)
            return self._extract_translation_text(result)

    def _translate_text(self):
        if inspect.iscoroutinefunction(Translator.translate):
            return asyncio.run(self._translate_async())

        result = Translator().translate(self.text, src=self.src_lang, dest=self.dest_lang)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        return self._extract_translation_text(result)

    def _extract_translation_text(self, result):
        translated_text = getattr(result, "text", None)
        if translated_text is None:
            raise RuntimeError(f"Unexpected translation result type: {type(result).__name__}")
        return translated_text


class PdfSentenceMinerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spanish PDF Sentence Miner")
        self.resize(1500, 950)

        self.translation_cache = {}
        self.thread_pool = QThreadPool.globalInstance()
        self.current_request_id = 0

        self.doc = None
        self.current_pdf_path = None
        self.current_page_index = 0
        self.zoom_factor = 2.0

        self.page_words = []
        self.page_line_words = {}
        self.page_word_order = []
        self.page_word_index = {}
        self.highlight_bboxes = []
        self.selection_anchor_key = None

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

        self._build_ui()
        self._apply_ui_scale()
        self._refresh_anki_status(initial=True)
        self._restore_last_session()

    def _build_ui(self):
        self._build_toolbar()

        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        viewer_container = QWidget()
        viewer_layout = QVBoxLayout(viewer_container)
        viewer_layout.setContentsMargins(8, 8, 8, 8)

        self.page_info_label = QLabel("No PDF loaded")
        viewer_layout.addWidget(self.page_info_label)

        self.pdf_label = ClickablePdfLabel()
        self.pdf_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.pdf_label.clicked.connect(self._on_pdf_click)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setWidget(self.pdf_label)
        viewer_layout.addWidget(self.scroll_area)

        self.right_panel = self._build_right_panel()

        main_splitter.addWidget(viewer_container)
        main_splitter.addWidget(self.right_panel)
        main_splitter.setSizes([1100, 380])

        self.setCentralWidget(main_splitter)

        status = QStatusBar()
        self.setStatusBar(status)
        self.anki_status_label = QLabel("Anki: checking...")
        status.addPermanentWidget(self.anki_status_label)

    def _build_toolbar(self):
        toolbar = QToolBar("PDF Tools")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_action = QAction("Open PDF", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_pdf_dialog)
        toolbar.addAction(open_action)

        prev_action = QAction("Prev Page", self)
        prev_action.setShortcut(QKeySequence(Qt.Key.Key_Left))
        prev_action.triggered.connect(self._prev_page)
        toolbar.addAction(prev_action)

        next_action = QAction("Next Page", self)
        next_action.setShortcut(QKeySequence(Qt.Key.Key_Right))
        next_action.triggered.connect(self._next_page)
        toolbar.addAction(next_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Page:"))
        self.page_input = QLineEdit()
        self.page_input.setMaximumWidth(90)
        self.page_input.setPlaceholderText("1")
        self.page_input.setValidator(QIntValidator(1, 1, self))
        self.page_input.returnPressed.connect(self._go_to_page)
        toolbar.addWidget(self.page_input)
        self.go_page_button = QPushButton("Go")
        self.go_page_button.clicked.connect(self._go_to_page)
        toolbar.addWidget(self.go_page_button)

        toolbar.addSeparator()
        zoom_out_action = QAction("Zoom -", self)
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.triggered.connect(self._zoom_out)
        toolbar.addAction(zoom_out_action)

        zoom_in_action = QAction("Zoom +", self)
        zoom_in_action.setShortcut(QKeySequence("Ctrl+="))
        zoom_in_action.triggered.connect(self._zoom_in)
        toolbar.addAction(zoom_in_action)

        fit_width_action = QAction("Fit Width", self)
        fit_width_action.triggered.connect(self._fit_width)
        toolbar.addAction(fit_width_action)

        toolbar.addSeparator()
        self.ui_down_button = QPushButton("A-")
        self.ui_down_button.clicked.connect(self._decrease_ui_scale)
        toolbar.addWidget(self.ui_down_button)
        self.ui_up_button = QPushButton("A+")
        self.ui_up_button.clicked.connect(self._increase_ui_scale)
        toolbar.addWidget(self.ui_up_button)

        toolbar.addSeparator()
        start_anki_action = QAction("Start Anki", self)
        start_anki_action.triggered.connect(self._start_anki)
        toolbar.addAction(start_anki_action)

        refresh_anki_action = QAction("Check Anki", self)
        refresh_anki_action.triggered.connect(self._refresh_anki_status)
        toolbar.addAction(refresh_anki_action)

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

        layout.addStretch(1)
        self._update_action_buttons()

        return panel

    def _set_status(self, message, timeout_ms=4000):
        self.statusBar().showMessage(message, timeout_ms)

    def _open_pdf_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if not path:
            return
        self._load_pdf(path)

    def _load_pdf(self, path, initial_page_index=0):
        try:
            self.doc = fitz.open(path)
        except Exception as exc:
            QMessageBox.critical(self, "PDF Error", f"Failed to open PDF:\n{exc}")
            return

        self.current_pdf_path = path
        if self.doc and self.doc.page_count > 0:
            self.current_page_index = max(0, min(initial_page_index, self.doc.page_count - 1))
        else:
            self.current_page_index = 0
        if self.doc and self.doc.page_count > 0:
            self.page_input.setValidator(QIntValidator(1, self.doc.page_count, self))
        self._clear_selection_state()
        self._render_current_page()
        self._reset_scroll_to_top()
        self._persist_last_session()
        self._set_status(f"Opened {os.path.basename(path)}")

    def _render_current_page(self):
        if not self.doc:
            self.pdf_label.clear()
            self.page_info_label.setText("No PDF loaded")
            return

        page = self.doc.load_page(self.current_page_index)
        matrix = fitz.Matrix(self.zoom_factor, self.zoom_factor)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()

        if self.highlight_bboxes:
            painter = QPainter(image)
            painter.setPen(QPen(Qt.GlobalColor.red, 2))
            for x0, y0, x1, y1 in self.highlight_bboxes:
                painter.drawRect(
                    int(x0 * self.zoom_factor),
                    int(y0 * self.zoom_factor),
                    max(1, int((x1 - x0) * self.zoom_factor)),
                    max(1, int((y1 - y0) * self.zoom_factor)),
                )
            painter.end()

        pixmap = QPixmap.fromImage(image)
        self.pdf_label.setPixmap(pixmap)
        self.pdf_label.resize(pixmap.size())

        self.page_words = page.get_text("words")
        self.page_word_order = sorted(
            self.page_words,
            key=lambda w: (int(w[5]), int(w[6]), int(w[7]), float(w[1]), float(w[0])),
        )
        self.page_word_index = {self._word_key(word): idx for idx, word in enumerate(self.page_word_order)}
        self.page_line_words = self._build_line_index(self.page_words)

        display_name = os.path.basename(self.current_pdf_path) if self.current_pdf_path else ""
        self.page_info_label.setText(
            f"{display_name} | Page {self.current_page_index + 1}/{self.doc.page_count} | Zoom {self.zoom_factor:.2f}x"
        )
        self.page_input.setText(str(self.current_page_index + 1))

    def _build_line_index(self, words):
        line_map = {}
        for word in words:
            key = (int(word[5]), int(word[6]))
            line_map.setdefault(key, []).append(word)

        for key in line_map:
            line_map[key].sort(key=lambda item: item[0])

        return line_map

    def _prev_page(self):
        if not self.doc or self.current_page_index <= 0:
            return
        self.current_page_index -= 1
        self._clear_selection_state()
        self._render_current_page()
        self._reset_scroll_to_top()
        self._persist_last_session()

    def _next_page(self):
        if not self.doc or self.current_page_index >= self.doc.page_count - 1:
            return
        self.current_page_index += 1
        self._clear_selection_state()
        self._render_current_page()
        self._reset_scroll_to_top()
        self._persist_last_session()

    def _zoom_in(self):
        if not self.doc:
            return
        self.zoom_factor = min(4.0, self.zoom_factor + 0.25)
        self._render_current_page()

    def _zoom_out(self):
        if not self.doc:
            return
        self.zoom_factor = max(0.5, self.zoom_factor - 0.25)
        self._render_current_page()

    def _fit_width(self):
        if not self.doc:
            return

        page = self.doc.load_page(self.current_page_index)
        available = max(200, self.scroll_area.viewport().width() - 24)
        self.zoom_factor = available / page.rect.width
        self.zoom_factor = max(0.5, min(4.0, self.zoom_factor))
        self._render_current_page()

    def _go_to_page(self):
        if not self.doc:
            return

        page_text = self.page_input.text().strip()
        if not page_text:
            return

        try:
            requested_page = int(page_text)
        except ValueError:
            self._set_status("Invalid page number")
            return

        if requested_page < 1 or requested_page > self.doc.page_count:
            self._set_status(f"Page must be between 1 and {self.doc.page_count}")
            return

        self.current_page_index = requested_page - 1
        self._clear_selection_state()
        self._render_current_page()
        self._reset_scroll_to_top()
        self._persist_last_session()

    def _apply_ui_scale(self):
        scaled_font = QFont(self.base_font)
        current_size = scaled_font.pointSizeF()
        if current_size <= 0:
            current_size = 10.0
        scaled_font.setPointSizeF(current_size * self.ui_scale)
        QApplication.instance().setFont(scaled_font)
        self._set_status(f"UI scale: {int(self.ui_scale * 100)}%", 1500)

    def _increase_ui_scale(self):
        self.ui_scale = min(self.max_ui_scale, self.ui_scale + 0.1)
        self._apply_ui_scale()

    def _decrease_ui_scale(self):
        self.ui_scale = max(self.min_ui_scale, self.ui_scale - 0.1)
        self._apply_ui_scale()

    def _clear_selection_state(self):
        self.highlight_bboxes = []
        self.selection_anchor_key = None
        self.selected_word = ""
        self.selected_sentence = ""
        self.selected_translation = ""
        self._update_selection_panel()
        self._update_action_buttons()

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
            x0, y0, x1, y1 = word[0], word[1], word[2], word[3]
            if x0 <= x_pdf <= x1 and y0 <= y_pdf <= y1:
                hit_word = word
                break

        if not hit_word:
            return

        raw_word = hit_word[4]
        clean_word = self._clean_word(raw_word)
        if not clean_word:
            return

        shift_pressed = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        selected_words = self._resolve_selected_words(hit_word, shift_pressed)

        cleaned_words = []
        for selected in selected_words:
            cleaned = self._clean_word(selected[4])
            if cleaned:
                cleaned_words.append(cleaned)

        if not cleaned_words:
            return

        self.highlight_bboxes = [(w[0], w[1], w[2], w[3]) for w in selected_words]
        self.selected_word = " ".join(cleaned_words)
        self.selected_sentence = self._extract_context_for_selection(selected_words)
        self.selected_translation = "Translating..."
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

    def _clean_word(self, value):
        start = 0
        end = len(value)

        while start < end and not (value[start].isalpha() or value[start].isdigit() or value[start] == "_"):
            start += 1

        while end > start and not (value[end - 1].isalpha() or value[end - 1].isdigit() or value[end - 1] == "_"):
            end -= 1

        return value[start:end].strip()

    def _extract_line_context(self, word):
        line_key = (int(word[5]), int(word[6]))
        line_words = self.page_line_words.get(line_key, [])
        if not line_words:
            return word[4]

        text = " ".join(item[4] for item in line_words)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_context_for_selection(self, selected_words):
        if not selected_words:
            return ""

        ordered_line_keys = []
        seen = set()
        for word in selected_words:
            key = (int(word[5]), int(word[6]))
            if key not in seen:
                seen.add(key)
                ordered_line_keys.append(key)

        lines = []
        for line_key in ordered_line_keys:
            line_words = self.page_line_words.get(line_key, [])
            if not line_words:
                continue
            line_text = " ".join(item[4] for item in line_words)
            line_text = re.sub(r"\s+", " ", line_text).strip()
            if line_text:
                lines.append(line_text)

        return "\n".join(lines)

    def _request_translation(self, text):
        key = ("es", "en", text)
        if key in self.translation_cache:
            self.selected_translation = self.translation_cache[key]
            self._update_selection_panel()
            self._update_action_buttons()
            return

        self.current_request_id += 1
        request_id = self.current_request_id

        task = TranslateTask(request_id, text, "es", "en")
        task.signals.finished.connect(self._on_translation_done)
        task.signals.failed.connect(self._on_translation_failed)
        self.thread_pool.start(task)

    def _on_translation_done(self, request_id, source_text, translated_text):
        if request_id != self.current_request_id:
            return

        key = ("es", "en", source_text)
        self.translation_cache[key] = translated_text
        self.selected_translation = translated_text
        self._update_selection_panel()
        self._update_action_buttons()

    def _on_translation_failed(self, request_id, error_message):
        if request_id != self.current_request_id:
            return

        self.selected_translation = f"Translation error: {error_message}"
        self._update_selection_panel()
        self._update_action_buttons()

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
        connected = test_anki_connection()
        self.is_anki_connected = connected

        if connected:
            self.anki_status_label.setText("Anki: connected")
            self._set_status("Connected to Anki", 2000 if not initial else 1000)
        else:
            self.anki_status_label.setText("Anki: not connected")
            if not initial:
                self._set_status("Could not reach AnkiConnect", 3000)

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
            handle.write(f"{sentence}\n")
            handle.write(f"{target_word}\n")
            handle.write(f"{translation}\n")

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
            "last_session": {
                "pdf_path": "",
                "page_index": 0,
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

        last_session = self.user_data.get("last_session")
        if not isinstance(last_session, dict):
            last_session = {}
        analytics = self.user_data.get("analytics")
        if not isinstance(analytics, dict):
            analytics = {}

        self.user_data["last_session"] = {
            "pdf_path": str(last_session.get("pdf_path") or ""),
            "page_index": int(last_session.get("page_index") or 0),
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

    def _persist_last_session(self):
        if not self.current_pdf_path:
            return

        self.user_data["last_session"] = {
            "pdf_path": self.current_pdf_path,
            "page_index": int(self.current_page_index),
        }
        self._save_user_data()

    def _restore_last_session(self):
        last_session = self.user_data.get("last_session", {})
        pdf_path = str(last_session.get("pdf_path") or "")
        page_index = int(last_session.get("page_index") or 0)

        if not pdf_path:
            return

        if not Path(pdf_path).exists():
            return

        self._load_pdf(pdf_path, initial_page_index=page_index)

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

    def _reset_scroll_to_top(self):
        if self.scroll_area and self.scroll_area.verticalScrollBar():
            self.scroll_area.verticalScrollBar().setValue(0)


def main():
    app = QApplication(sys.argv)
    window = PdfSentenceMinerWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
