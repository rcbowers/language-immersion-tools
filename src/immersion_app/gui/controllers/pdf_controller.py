from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QMessageBox

from immersion_app.core.mode import WorkspaceMode
from immersion_app.core.pdf_render_cache import PdfRenderCache
from immersion_app.core.perf import perf_span, perf_timed
from immersion_app.core.recent_files import add_recent_file
from immersion_app.core.user_data import save_user_data
from immersion_app.gui.theme import Theme


SLOW_RENDER_STATUS_DELAY_MS = 150


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
        # Async rendering state. ``_generation`` changes whenever cached/in-flight renders become invalid
        # (document opened/closed); ``_request_id`` identifies the render the UI is currently waiting for.
        self._cache = PdfRenderCache()
        self._generation = 0
        self._request_id = 0
        self._inflight: set = set()
        self.render_pending = False
        self._word_geometry: list[tuple[QRect, str]] = []
        if hasattr(pdf_service, "page_rendered"):
            pdf_service.page_rendered.connect(self._on_page_rendered)
            pdf_service.page_render_failed.connect(self._on_page_render_failed)

    def load_pdf(self, path: str, initial_page_index: int = 0):
        try:
            doc = self.pdf_service.load_document(path)
        except Exception as exc:
            QMessageBox.critical(self.window, "PDF Error", f"Failed to open PDF:\n{exc}")
            return
        self.reset_render_state()
        self.current_pdf_path = path
        self.window.current_pdf_path = path
        self.current_page_index = max(0, min(initial_page_index, doc.page_count - 1))
        self.window.current_page_index = self.current_page_index
        self.window.current_source_name = Path(path).name
        self.window.current_source_location = f"Page {self.current_page_index + 1}"
        if hasattr(self.window, "usage_tracker"):
            self.window.usage_tracker.set_pdf_page_index(self.current_page_index)
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

    # ------------------------------------------------------------------ rendering

    def reset_render_state(self):
        """Forget cached and in-flight renders (document opened/closed)."""
        self._generation += 1
        self._request_id += 1
        self._cache.clear()
        self._inflight.clear()
        self.render_pending = False

    def _is_dark(self) -> bool:
        return bool(getattr(self.window.appearance_manager.current_mode, "is_dark", False))

    def _cache_key(self, page_index: int, dark: bool | None = None):
        return PdfRenderCache.make_key(
            self.current_pdf_path, page_index, self.zoom_factor, self._is_dark() if dark is None else dark
        )

    @perf_timed("pdf_controller.render_current_page")
    def render_current_page(self):
        """Show the current page: instantly from the cache, otherwise via a background render."""
        if self.pdf_service.doc is None:
            return
        cached = self._cache.get(self._cache_key(self.current_page_index))
        if cached is not None:
            self._request_id += 1  # supersede any render still in flight
            self.render_pending = False
            self._apply_page(cached)
            return
        self._request_render()

    def _request_render(self):
        self._request_id += 1
        request_id = self._request_id
        generation = self._generation
        dark = self._is_dark()
        zoom = self.zoom_factor
        page_index = self.current_page_index
        tag = self._cache_key(page_index, dark)
        self.render_pending = True
        self._inflight.add(tag)

        def is_stale() -> bool:
            return generation != self._generation or request_id != self._request_id

        self.pdf_service.render_async(page_index, zoom, dark, request_id, generation, tag, is_stale, priority=1)
        # Keep the previous page on screen; only tell the user if the render is actually slow.
        QTimer.singleShot(SLOW_RENDER_STATUS_DELAY_MS, lambda: self._notify_if_still_rendering(request_id))

    def _notify_if_still_rendering(self, request_id: int):
        if self.render_pending and request_id == self._request_id and hasattr(self.window, "_set_status"):
            self.window._set_status("Rendering page...")

    def _prefetch_neighbors(self):
        """Warm the cache with the pages the reader is most likely to open next."""
        page_count = self.pdf_service.page_count()
        dark = self._is_dark()
        zoom = self.zoom_factor
        generation = self._generation
        for page_index in (self.current_page_index + 1, self.current_page_index - 1):
            if not 0 <= page_index < page_count:
                continue
            tag = self._cache_key(page_index, dark)
            if tag in self._cache or tag in self._inflight:
                continue
            self._inflight.add(tag)

            def is_stale(zoom=zoom, dark=dark, generation=generation) -> bool:
                return generation != self._generation or zoom != self.zoom_factor or dark != self._is_dark()

            self.pdf_service.render_async(page_index, zoom, dark, -1, generation, tag, is_stale, priority=0)

    def _on_page_rendered(self, request_id, generation, tag, result):
        self._inflight.discard(tag)
        if result is None or generation != self._generation:
            return  # skipped as stale, or belongs to a document that is no longer open
        self._cache.put(tag, result)
        if request_id == self._request_id:
            self.render_pending = False
            self._apply_page(result)

    def _on_page_render_failed(self, request_id, generation, tag, message):
        self._inflight.discard(tag)
        if generation != self._generation:
            return
        if request_id == self._request_id:
            self.render_pending = False
            if hasattr(self.window, "_set_status"):
                self.window._set_status(f"Could not render page: {message}")

    def _zoomed_rect(self, x0, y0, x1, y1) -> QRect:
        return QRect(
            int(x0 * self.zoom_factor),
            int(y0 * self.zoom_factor),
            max(1, int((x1 - x0) * self.zoom_factor)),
            max(1, int((y1 - y0) * self.zoom_factor)),
        )

    def refresh_word_highlights(self):
        """Rebuild the seen/new word backgrounds (vocabulary or theme changed). No re-rasterizing."""
        vocabulary = self.window.analytics_vocabulary
        seen, new = Theme.to_qcolor(Theme.HL_SEEN), Theme.to_qcolor(Theme.HL_NEW)
        items = [(rect, seen if word in vocabulary else new) for rect, word in self._word_geometry]
        self.window.pdf_label.set_word_highlights(items)

    def _rebuild_word_geometry(self):
        """Per-page, vocabulary-independent word rects + normalised text (computed once per applied page)."""
        clean = self.window._clean_word
        geometry = []
        for x0, y0, x1, y1, text, *_rest in self.page_words:
            cleaned = clean(text)
            if cleaned:
                geometry.append((self._zoomed_rect(x0, y0, x1, y1), cleaned.lower()))
        self._word_geometry = geometry

    def refresh_highlights(self):
        """Move the selection highlight (and popover) without touching the page image."""
        rects = [self._zoomed_rect(*bbox) for bbox in self.selection.pdf.highlight_bboxes]
        self.window.pdf_label.set_selection_rects(rects, Theme.to_qcolor(Theme.HL_SELECTED))
        if (
            self.window.mode_manager.current_mode == WorkspaceMode.PDF
            and self.selection.pdf.selected_words
            and self.selection.translation
            and self.selection.translation != "translating..."
            and not self.selection.translation.startswith("Translation error:")
        ):
            self.window._show_translation_popover()
        elif not self.selection.pdf.selected_words:
            self.window._close_popover()

    def _apply_page(self, result):
        """Display a rendered page. Runs once per page/zoom/theme change, not per click."""
        with perf_span("pdf_controller.apply_page"):
            image = QImage(result.samples, result.width, result.height, result.stride, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(image)  # copies, so ``result.samples`` may stay cached
            self.window.pdf_label.setPixmap(pixmap)
            self.window.pdf_label.resize(pixmap.size())
            self.page_words = result.words
            self.page_word_order = result.word_order
            self.page_line_words = result.line_map
            self.page_word_index = {self.pdf_service.word_key(word): idx for idx, word in enumerate(result.word_order)}
            self._rebuild_word_geometry()
            self.refresh_word_highlights()
            self.window.current_source_location = f"Page {self.current_page_index + 1}"
            if hasattr(self.window, "usage_tracker"):
                self.window.usage_tracker.set_pdf_page_index(self.current_page_index)
            self.window._update_source_summary()
            self.window.command_bar.set_page_info(self.current_page_index + 1, result.page_count)
            self.window.pdf_status_bar.set_zoom_level(self.zoom_factor)
            if hasattr(self.window, "shortcut_panel") and self.current_pdf_path:
                self.window.shortcut_panel.set_current_context(self.current_pdf_path, self.current_page_index, WorkspaceMode.PDF)
                is_complete = self.window.completion_tracker.is_page_complete(self.current_pdf_path, self.current_page_index)
                self.window.shortcut_panel.update_completion_state(is_complete)
            words = list(self.window._iter_unique_clean_words(word[4] for word in self.page_word_order))
            self.mining_controller.prefetch_translations(words)
            self.refresh_highlights()
        self._prefetch_neighbors()

    @perf_timed("pdf_controller.click_at")
    def click_at(self, point, modifiers):
        if not self.page_words:
            return
        x_pdf = point.x() / self.zoom_factor
        y_pdf = point.y() / self.zoom_factor
        hit_word = self.pdf_service.word_at_point(self.page_word_order, x_pdf, y_pdf)
        if not hit_word:
            self.mining_controller.clear_selection()
            self.refresh_highlights()
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
        display_word = " ".join(cleaned_words)
        # For phrases, join raw PDF tokens (which retain attached punctuation like "Bueno,")
        # so the translation model receives properly punctuated input.
        if len(selected_words) == 1:
            translation_text = display_word
        else:
            translation_text = " ".join(w[4] for w in selected_words).strip()
        self.selection.pdf.anchor_key = anchor_key
        self.selection.set_pdf_selection(
            word=display_word,
            sentence=self.pdf_service.extract_context(selected_words, self.page_line_words),
            selected_words=list(selected_words),
            highlight_bboxes=self.pdf_service.merge_highlight_bboxes(selected_words),
        )
        self.window.current_source_location = f"Page {self.current_page_index + 1}"
        self.refresh_highlights()
        self.mining_controller.request_translation(translation_text)

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
            highlight_bboxes=self.pdf_service.merge_highlight_bboxes([hit_word]),
        )
        self.window.current_source_location = f"Page {self.current_page_index + 1}"
        self.refresh_highlights()
        self.mining_controller.request_translation(word_text)

    def jump_to_page(self, page_number: int):
        if self.pdf_service.doc is None or not (1 <= page_number <= self.pdf_service.doc.page_count):
            return
        self.current_page_index = page_number - 1
        self.window.current_page_index = self.current_page_index
        self.mining_controller.clear_selection()
        self.render_current_page()
        self.window._reset_pdf_scroll_position()
        if hasattr(self.window, "usage_tracker"):
            self.window.usage_tracker.record_activity()
        if self.content_browser_manager and self.current_pdf_path:
            self.content_browser_manager.update_last_position(
                self.current_pdf_path,
                {"page_index": self.current_page_index}
            )
        self.window._persist_session()

    def prev_page(self):
        if self.pdf_service.doc is None or self.current_page_index <= 0:
            return
        self.current_page_index -= 1
        self.window.current_page_index = self.current_page_index
        self.mining_controller.clear_selection()
        self.render_current_page()
        self.window._reset_pdf_scroll_position()
        if hasattr(self.window, "usage_tracker"):
            self.window.usage_tracker.record_activity()
        if self.content_browser_manager and self.current_pdf_path:
            self.content_browser_manager.update_last_position(
                self.current_pdf_path,
                {"page_index": self.current_page_index}
            )
        self.window._persist_session()

    def next_page(self):
        if self.pdf_service.doc is None or self.current_page_index >= self.pdf_service.doc.page_count - 1:
            return
        self.current_page_index += 1
        self.window.current_page_index = self.current_page_index
        self.mining_controller.clear_selection()
        self.render_current_page()
        self.window._reset_pdf_scroll_position()
        if hasattr(self.window, "usage_tracker"):
            self.window.usage_tracker.record_activity()
        if self.content_browser_manager and self.current_pdf_path:
            self.content_browser_manager.update_last_position(
                self.current_pdf_path,
                {"page_index": self.current_page_index}
            )
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
        page_width, _page_height = self.pdf_service.page_size(self.current_page_index)
        reading_column = self.window.scroll_area.parent()
        available = max(200, reading_column.width() - 72)
        self.zoom_factor = max(0.5, min(4.0, (available / page_width) - 0.25))
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
