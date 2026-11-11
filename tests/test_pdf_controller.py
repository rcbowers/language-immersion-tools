import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from immersion_app.core.selection_state import SelectionState
from immersion_app.core.pdf_service import PDFService
from immersion_app.gui.controllers.pdf_controller import PDFController


class _PdfService:
    def word_key(self, word):
        return word

    def word_at_point(self, word_order, x_pdf, y_pdf):
        return word_order[0]

    def resolve_selected_words(self, hit_word, shift_pressed, anchor_key, page_word_order, page_word_index):
        return [hit_word], hit_word

    def extract_context(self, selected_words, line_map):
        return "hola mundo"

    def merge_highlight_bboxes(self, selected_words):
        # Pure geometry helper: reuse the real implementation.
        return PDFService.merge_highlight_bboxes(self, selected_words)


class _MiningController:
    def __init__(self):
        self.translation_requests = []

    def clear_selection(self):
        pass

    def request_translation(self, text):
        self.translation_requests.append(text)

    def prefetch_translations(self, texts):
        pass


class PDFControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_click_updates_selection_and_requests_translation(self):
        window = SimpleNamespace(
            _clean_word=lambda text: text,
            _update_source_summary=lambda: None,
            _update_command_bar_stats=lambda: None,
            _show_translation_popover=lambda: None,
            analytics_vocabulary=set(),
            current_source_location="",
            current_source_name="book.pdf",
            mode_manager=SimpleNamespace(current_mode=None),
            pdf_label=SimpleNamespace(setPixmap=lambda _pixmap: None, resize=lambda _size: None),
            command_bar=SimpleNamespace(set_page_info=lambda *_args: None),
            pdf_status_bar=SimpleNamespace(set_zoom_level=lambda *_args: None),
            appearance_manager=SimpleNamespace(current_mode=None),
            shortcut_panel=SimpleNamespace(set_current_context=lambda *_args: None, update_completion_state=lambda *_args: None),
            completion_tracker=SimpleNamespace(is_page_complete=lambda *_args: False),
            _iter_unique_clean_words=lambda values: list(values),
        )
        selection = SelectionState()
        mining_controller = _MiningController()
        controller = PDFController(window, _PdfService(), selection, mining_controller)
        controller.page_words = [(0.0, 0.0, 10.0, 10.0, "hola", 0, 0, 0)]
        controller.page_word_order = list(controller.page_words)
        controller.page_word_index = {controller.page_word_order[0]: 0}
        controller.page_line_words = {(0, 0): controller.page_words}
        controller.render_current_page = lambda: None

        controller.click_at(QPoint(5, 5), Qt.KeyboardModifier.NoModifier)

        self.assertEqual(selection.word, "hola")
        self.assertEqual(selection.sentence, "hola mundo")
        self.assertEqual(mining_controller.translation_requests, ["hola"])


if __name__ == "__main__":
    unittest.main()
