#!/usr/bin/env python3
"""PDF sentence miner window."""

import os
from pathlib import Path

import fitz
from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QImage, QIntValidator, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from base_miner_window import AbstractSentenceMinerWindow


class ClickablePdfLabel(QLabel):
    clicked = Signal(QPoint, object)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(event.position().toPoint(), event.modifiers())
        super().mousePressEvent(event)


class PdfSentenceMinerWindow(AbstractSentenceMinerWindow):
    SUPPORTED_CONTENT_FILTER = "Content Files (*.pdf *.mp4 *.mkv *.avi *.mov *.webm)"

    def __init__(self):
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
        self.page_input = None
        self.page_info_label = None
        self.pdf_label = None
        self.scroll_area = None
        self.prev_page_button = None
        self.next_page_button = None

        super().__init__("Spanish PDF Sentence Miner")

    def _build_mode_toolbar(self):
        toolbar = QToolBar("PDF Tools")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        content_menu = QMenu("Content", self)
        self._add_menu_action(content_menu, "Open content", self._open_content_dialog, shortcuts="Ctrl+O")
        self._add_toolbar_menu_button(toolbar, "Content", content_menu)

        toolbar.addSeparator()
        view_menu = QMenu("View", self)
        self._add_menu_action(view_menu, "PDF zoom in", self._zoom_in, shortcuts="Ctrl+Shift+=")
        self._add_menu_action(view_menu, "PDF zoom out", self._zoom_out, shortcuts="Ctrl+Shift+-")
        self._add_menu_action(view_menu, "Fit width", self._fit_width)
        self._add_toolbar_menu_button(toolbar, "View", view_menu)

        toolbar.addSeparator()
        self._build_common_toolbar_menus(toolbar)

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

    def _build_viewer_panel(self):
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

        self.prev_page_button = QPushButton("<", self.scroll_area.viewport())
        self.prev_page_button.setShortcut(QKeySequence(Qt.Key.Key_Left))
        self.prev_page_button.clicked.connect(self._prev_page)
        self.prev_page_button.raise_()

        self.next_page_button = QPushButton(">", self.scroll_area.viewport())
        self.next_page_button.setShortcut(QKeySequence(Qt.Key.Key_Right))
        self.next_page_button.clicked.connect(self._next_page)
        self.next_page_button.raise_()

        self.scroll_area.viewport().installEventFilter(self)
        self._position_overlay_nav_buttons()

        return viewer_container

    def eventFilter(self, watched, event):
        if self.scroll_area and watched == self.scroll_area.viewport() and event.type() == QEvent.Type.Resize:
            self._position_overlay_nav_buttons()
        return super().eventFilter(watched, event)

    def _position_overlay_nav_buttons(self):
        if not self.scroll_area or not self.prev_page_button or not self.next_page_button:
            return

        viewport = self.scroll_area.viewport()
        margin = 10
        y = max(margin, viewport.height() - self.prev_page_button.sizeHint().height() - margin)

        self.prev_page_button.adjustSize()
        self.next_page_button.adjustSize()

        self.prev_page_button.move(margin, y)
        self.next_page_button.move(max(margin, viewport.width() - self.next_page_button.width() - margin), y)

    def _open_pdf_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if not path:
            return
        self._load_pdf(path)

    def _open_content_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open content", "", self.SUPPORTED_CONTENT_FILTER)
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext == ".pdf":
            self._load_pdf(path)
            return
        self._switch_to_video_mode(path)

    def _switch_to_video_mode(self, video_path):
        from video_miner_window import VideoSentenceMinerWindow

        window = VideoSentenceMinerWindow()
        window.show()
        window._load_video(video_path)
        window.user_data["mode"] = "video"
        window._save_user_data()
        self.close()

    def _load_pdf(self, path, initial_page_index=0):
        try:
            self.doc = fitz.open(path)
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "PDF Error", f"Failed to open PDF:\n{exc}")
            return

        self.current_pdf_path = path
        if self.doc and self.doc.page_count > 0:
            self.current_page_index = max(0, min(initial_page_index, self.doc.page_count - 1))
            self.page_input.setValidator(QIntValidator(1, self.doc.page_count, self))
        else:
            self.current_page_index = 0

        self._clear_selection_state()
        self.highlight_bboxes = []
        self.selection_anchor_key = None
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

        clean_word = self._clean_word(hit_word[4])
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

    def _extract_line_context(self, word):
        line_key = (int(word[5]), int(word[6]))
        line_words = self.page_line_words.get(line_key, [word])
        return " ".join(item[4] for item in line_words)

    def _extract_context_for_selection(self, selected_words):
        if not selected_words:
            return ""
        first_word = selected_words[0]
        return self._extract_line_context(first_word)

    def _prev_page(self):
        if not self.doc or self.current_page_index <= 0:
            return
        self.current_page_index -= 1
        self._clear_viewer_state()
        self._render_current_page()
        self._reset_scroll_to_top()
        self._persist_last_session()

    def _next_page(self):
        if not self.doc or self.current_page_index >= self.doc.page_count - 1:
            return
        self.current_page_index += 1
        self._clear_viewer_state()
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
        self.zoom_factor = max(0.5, min(4.0, available / page.rect.width))
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
        self._clear_viewer_state()
        self._render_current_page()
        self._reset_scroll_to_top()
        self._persist_last_session()

    def _clear_viewer_state(self):
        self.highlight_bboxes = []
        self.selection_anchor_key = None
        self._clear_selection_state()

    def _persist_last_session(self):
        if not self.current_pdf_path:
            return

        self.user_data["mode"] = "pdf"
        self.user_data["last_session"]["pdf_path"] = self.current_pdf_path
        self.user_data["last_session"]["page_index"] = int(self.current_page_index)
        self._save_user_data()

    def _restore_session_state(self):
        last_session = self.user_data.get("last_session", {})
        pdf_path = str(last_session.get("pdf_path") or "")
        page_index = int(last_session.get("page_index") or 0)

        if not pdf_path:
            return

        from pathlib import Path

        if not Path(pdf_path).exists():
            return

        self._load_pdf(pdf_path, initial_page_index=page_index)

    def _reset_scroll_to_top(self):
        if self.scroll_area and self.scroll_area.verticalScrollBar():
            self.scroll_area.verticalScrollBar().setValue(0)
