from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import QMessageBox

from immersion_app.core.appearance_manager import AppearanceMode
from immersion_app.core.mode import WorkspaceMode
from immersion_app.core.recent_files import add_recent_file
from immersion_app.core.user_data import save_user_data
from immersion_app.gui.theme import Theme


class PDFController:
    def __init__(self, window, pdf_service, selection_state, mining_controller, content_browser_manager=None):
        self.window = window
        self.pdf_service = pdf_service
        self.selection = selection_state
        self.mining_controller = mining_controller
        self.content_browser_manager = content_browser_manager
        self.current_pdf_path = ""
        self.current_page_index = 0
        self.zoom_factor = 2.0
        self.page_words = []
        self.page_word_order = []
        self.page_word_index = {}
        self.page_line_words = {}

    def load_pdf(self, path: str, initial_page_index: int = 0):
        try:
            doc = self.pdf_service.load_document(path)
        except Exception as exc:
            QMessageBox.critical(self.window, "PDF Error", f"Failed to open PDF:\n{exc}")
            return
        self.current_pdf_path = path
        self.current_page_index = max(0, min(initial_page_index, doc.page_count - 1))
        self.window.current_source_name = Path(path).name
        self.window.current_source_location = f"Page {self.current_page_index + 1}"
        self.mining_controller.clear_selection()
        QTimer.singleShot(0, self.fit_width)
        QTimer.singleShot(0, self.window._reset_pdf_scroll_position)
        self.window._update_source_summary()
        self.window._persist_session()
        self.window._set_status(f"Opened PDF: {Path(path).name}")
        self.window.command_bar.set_title(Path(path).name, f"{doc.page_count} pages")
        self.window.command_bar.set_file_loaded(True)
        self.window.command_bar.set_page_info(self.current_page_index + 1, doc.page_count)
        self.window._update_command_bar_stats()
        self.window.mode_manager.set_pdf_loaded(True)
        self.window.mode_manager.set_mode(WorkspaceMode.PDF, force=True)
        add_recent_file(self.window.user_data, str(path), "pdf", {"page_index": self.current_page_index})

        # Add to content browser
        if self.content_browser_manager:
            self.content_browser_manager.add_content(
                file_path=str(path),
                content_type="pdf",
                page_count=doc.page_count,
                last_position={"page_index": self.current_page_index}
            )

        save_user_data(self.window.user_data)

    def render_current_page(self):
        result = self.pdf_service.render_page(self.current_page_index, self.zoom_factor)
        if result is None:
            return
        image = QImage(result.samples, result.width, result.height, result.stride, QImage.Format.Format_RGB888).copy()
        if self.window.appearance_manager.current_mode == AppearanceMode.DARK:
            image.invertPixels()
        painter = QPainter(image)
        for word_obj in result.words:
            x0, y0, x1, y1, text = word_obj[0:5]
            cleaned_text = self.window._clean_word(text)
            if not cleaned_text:
                continue
            color = Theme.to_qcolor(Theme.HL_SEEN if cleaned_text.lower() in self.window.analytics_vocabulary else Theme.HL_NEW)
            painter.fillRect(
                int(x0 * self.zoom_factor),
                int(y0 * self.zoom_factor),
                max(1, int((x1 - x0) * self.zoom_factor)),
                max(1, int((y1 - y0) * self.zoom_factor)),
                color,
            )
        if self.selection.pdf.highlight_bboxes:
            selection_color = Theme.to_qcolor(Theme.HL_SELECTED)
            for x0, y0, x1, y1 in self.selection.pdf.highlight_bboxes:
                painter.fillRect(
                    int(x0 * self.zoom_factor),
                    int(y0 * self.zoom_factor),
                    max(1, int((x1 - x0) * self.zoom_factor)),
                    max(1, int((y1 - y0) * self.zoom_factor)),
                    selection_color,
                )
        painter.end()

        pixmap = QPixmap.fromImage(image)
        self.window.pdf_label.setPixmap(pixmap)
        self.window.pdf_label.resize(pixmap.size())
        self.page_words = result.words
        self.page_word_order = result.word_order
        self.page_line_words = result.line_map
        self.page_word_index = {self.pdf_service.word_key(word): idx for idx, word in enumerate(result.word_order)}
        self.window.current_source_location = f"Page {self.current_page_index + 1}"
        self.window._update_source_summary()
        self.window.command_bar.set_page_info(self.current_page_index + 1, result.page_count)
        self.window.pdf_status_bar.set_zoom_level(self.zoom_factor)
        if hasattr(self.window, "shortcut_panel") and self.current_pdf_path:
            self.window.shortcut_panel.set_current_context(self.current_pdf_path, self.current_page_index, WorkspaceMode.PDF)
            is_complete = self.window.completion_tracker.is_page_complete(self.current_pdf_path, self.current_page_index)
            self.window.shortcut_panel.update_completion_state(is_complete)
        words = list(self.window._iter_unique_clean_words(word[4] for word in self.page_word_order))
        self.mining_controller.prefetch_translations(words)
        if self.window.mode_manager.current_mode == WorkspaceMode.PDF and self.selection.pdf.selected_words and self.selection.translation and self.selection.translation != "translating..." and not self.selection.translation.startswith("Translation error:"):
            self.window._show_translation_popover()

    def click_at(self, point, modifiers):
        if not self.page_words:
            return
        x_pdf = point.x() / self.zoom_factor
        y_pdf = point.y() / self.zoom_factor
        hit_word = self.pdf_service.word_at_point(self.page_word_order, x_pdf, y_pdf)
        if not hit_word:
            self.mining_controller.clear_selection()
            return
        selected_words, anchor_key = self.pdf_service.resolve_selected_words(
            hit_word,
            bool(modifiers & Qt.KeyboardModifier.ShiftModifier),
            self.selection.pdf.anchor_key,
            self.page_word_order,
            self.page_word_index,
        )
        cleaned_words = [self.window._clean_word(selected[4]) for selected in selected_words if self.window._clean_word(selected[4])]
        if not cleaned_words:
            return
        self.selection.pdf.anchor_key = anchor_key
        self.selection.set_pdf_selection(
            word=" ".join(cleaned_words),
            sentence=self.pdf_service.extract_context(selected_words, self.page_line_words),
            selected_words=list(selected_words),
            highlight_bboxes=[(w[0], w[1], w[2], w[3]) for w in selected_words],
        )
        self.window.current_source_location = f"Page {self.current_page_index + 1}"
        self.render_current_page()
        self.mining_controller.request_translation(self.selection.word)

    def hover_at(self, point, modifiers):
        if not (modifiers & Qt.KeyboardModifier.ControlModifier):
            return
        if not self.page_words:
            return
        x_pdf = point.x() / self.zoom_factor
        y_pdf = point.y() / self.zoom_factor
        hit_word = self.pdf_service.word_at_point(self.page_word_order, x_pdf, y_pdf)
        if hit_word is None:
            return
        word_text = self.window._clean_word(hit_word[4])
        if not word_text or word_text == self.selection.word:
            return
        self.selection.pdf.anchor_key = self.pdf_service.word_key(hit_word)
        self.selection.set_pdf_selection(
            word=word_text,
            sentence=self.pdf_service.extract_context([hit_word], self.page_line_words),
            selected_words=[hit_word],
            highlight_bboxes=[(hit_word[0], hit_word[1], hit_word[2], hit_word[3])],
        )
        self.window.current_source_location = f"Page {self.current_page_index + 1}"
        self.render_current_page()
        self.mining_controller.request_translation(word_text)

    def jump_to_page(self, page_number: int):
        if self.pdf_service.doc is None or not (1 <= page_number <= self.pdf_service.doc.page_count):
            return
        self.current_page_index = page_number - 1
        self.mining_controller.clear_selection()
        self.render_current_page()
        self.window._reset_pdf_scroll_position()
        self.window._persist_session()

    def prev_page(self):
        if self.pdf_service.doc is None or self.current_page_index <= 0:
            return
        self.current_page_index -= 1
        self.mining_controller.clear_selection()
        self.render_current_page()
        self.window._reset_pdf_scroll_position()
        self.window._persist_session()

    def next_page(self):
        if self.pdf_service.doc is None or self.current_page_index >= self.pdf_service.doc.page_count - 1:
            return
        self.current_page_index += 1
        self.mining_controller.clear_selection()
        self.render_current_page()
        self.window._reset_pdf_scroll_position()
        self.window._persist_session()

    def zoom_in(self):
        if self.pdf_service.doc is not None:
            self.zoom_factor = min(4.0, self.zoom_factor + 0.25)
            self.render_current_page()

    def zoom_out(self):
        if self.pdf_service.doc is not None:
            self.zoom_factor = max(0.5, self.zoom_factor - 0.25)
            self.render_current_page()

    def reset_zoom(self):
        if self.pdf_service.doc is not None:
            self.zoom_factor = 2.0
            self.render_current_page()

    def fit_width(self):
        if self.pdf_service.doc is None:
            return
        page = self.pdf_service.doc.load_page(self.current_page_index)
        reading_column = self.window.scroll_area.parent()
        available = max(200, reading_column.width() - 72)
        self.zoom_factor = max(0.5, min(4.0, (available / page.rect.width) - 0.25))
        self.render_current_page()

    def selection_anchor_rect(self):
        if not self.selection.pdf.selected_words:
            return QRect()
        first_line_key = (int(self.selection.pdf.selected_words[0][5]), int(self.selection.pdf.selected_words[0][6]))
        first_line_words = [word for word in self.selection.pdf.selected_words if (int(word[5]), int(word[6])) == first_line_key]
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
        return QRect(self.window.pdf_label.mapTo(self.window, local_rect.topLeft()), local_rect.size())
