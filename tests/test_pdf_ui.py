import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QAbstractButton

from immersion_app.core.mode import WorkspaceMode
from immersion_app.gui.main_window import UnifiedSentenceMinerWindow
from immersion_app.gui.theme import Theme
from immersion_app.gui.widgets.command_bar import CommandBar
from immersion_app.gui.widgets.pdf_status_bar import PDFStatusBar


class PdfWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_command_bar_uses_compact_height(self):
        bar = CommandBar(user_data={})

        self.assertEqual(bar.height(), Theme.COMMAND_BAR_HEIGHT)
        self.assertEqual(bar.layout().contentsMargins().top(), 4)
        self.assertEqual(bar.layout().contentsMargins().bottom(), 4)

    def test_command_bar_activity_button_emits_signal(self):
        bar = CommandBar(user_data={})
        captured = []
        bar.analytics_requested.connect(lambda: captured.append(True))

        bar.analytics_button.click()

        self.assertEqual(captured, [True])

    def test_pdf_status_bar_shows_requested_instruction_text(self):
        bar = PDFStatusBar()

        self.assertEqual(bar.height(), Theme.STATUS_BAR_HEIGHT)
        instruction_text = bar.instruction_label.text()
        self.assertIn("Ctrl+hover to translate", instruction_text)
        self.assertIn("Shift+click to end of a phrase", instruction_text)
        self.assertIn("Ctrl+Space to add to Anki", instruction_text)

    def test_pdf_status_bar_has_no_console_toggle(self):
        bar = PDFStatusBar()

        self.assertFalse(hasattr(bar, "console_toggle_button"))
        self.assertFalse(hasattr(bar, "set_console_visible"))
        self.assertFalse(hasattr(PDFStatusBar, "console_toggled"))
        self.assertNotIn(">_", [button.text() for button in bar.findChildren(QAbstractButton)])

    def test_pdf_status_bar_zoom_label_click_emits_reset(self):
        bar = PDFStatusBar()
        captured = []
        bar.reset_zoom_clicked.connect(lambda: captured.append(True))

        bar.zoom_label.mousePressEvent(None)

        self.assertEqual(captured, [True])

    def test_pdf_status_bar_disconnected_anki_click_emits_refresh(self):
        bar = PDFStatusBar()
        captured = []
        bar.anki_status_clicked.connect(lambda: captured.append(True))
        bar.set_anki_status(False, checking=False)

        bar.anki_status_label.mousePressEvent(None)

        self.assertEqual(captured, [True])

    def test_pdf_status_bar_connected_anki_click_does_not_emit_refresh(self):
        bar = PDFStatusBar()
        captured = []
        bar.anki_status_clicked.connect(lambda: captured.append(True))
        bar.set_anki_status(True, checking=False)

        bar.anki_status_label.mousePressEvent(None)

        self.assertEqual(captured, [])

    def test_pdf_status_bar_right_side_order_is_usage_translation_anki_zoom(self):
        bar = PDFStatusBar()

        right_region = bar.layout().itemAt(2).widget()
        right_layout = right_region.layout()

        self.assertIs(right_layout.itemAt(0).widget(), bar.usage_tracking_label)
        self.assertEqual(right_layout.itemAt(1).widget().text(), "Translation: Offline")
        self.assertEqual(right_layout.itemAt(2).widget().text(), "Anki: Checking...")
        self.assertEqual(right_layout.itemAt(3).widget().layout().itemAt(0).widget().text(), "200%")


class WindowAnkiBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_refresh_anki_status_delegates_to_service(self):
        class _Service:
            def __init__(self):
                self.calls = 0

            def refresh_connection(self):
                self.calls += 1

        window = UnifiedSentenceMinerWindow.__new__(UnifiedSentenceMinerWindow)
        window.anki_service = _Service()

        UnifiedSentenceMinerWindow._refresh_anki_status(window)

        self.assertEqual(window.anki_service.calls, 1)

    def test_anki_connection_update_updates_pdf_status_bar(self):
        window = UnifiedSentenceMinerWindow.__new__(UnifiedSentenceMinerWindow)
        window.is_anki_connected = False
        window.anki_status_label = SimpleNamespace(text=None, setText=lambda value: setattr(window.anki_status_label, "text", value))
        window.health_label = SimpleNamespace(text=None, setText=lambda value: setattr(window.health_label, "text", value))
        window.translation_mode = "online"
        window.pdf_status_bar = PDFStatusBar()

        UnifiedSentenceMinerWindow._on_anki_connection_changed(window, True)

        self.assertTrue(window.is_anki_connected)
        self.assertEqual(window.anki_status_label.text, "Anki: connected")
        self.assertEqual(window.pdf_status_bar.anki_status_label.text(), "Anki: Connected ✓")



class PDFControllerActivityTests(unittest.TestCase):
    """Verify that PDF navigation actions record activity on the usage tracker."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_controller(self):
        from immersion_app.gui.controllers.pdf_controller import PDFController

        activity_calls = []

        window = SimpleNamespace(
            current_page_index=2,
            current_source_location="",
            usage_tracker=SimpleNamespace(
                record_activity=lambda: activity_calls.append(True),
                set_pdf_page_index=lambda idx: None,
            ),
            appearance_manager=SimpleNamespace(current_mode=None),
            analytics_vocabulary=set(),
            pdf_label=SimpleNamespace(setPixmap=lambda _: None, resize=lambda _: None),
            selection=SimpleNamespace(
                pdf=SimpleNamespace(highlight_bboxes=[], selected_words=[], anchor_key=None),
                translation="",
            ),
            mode_manager=SimpleNamespace(current_mode=WorkspaceMode.PDF),
            command_bar=SimpleNamespace(set_page_info=lambda *_: None),
            pdf_status_bar=SimpleNamespace(set_zoom_level=lambda *_: None),
            # intentionally no shortcut_panel — hasattr check in render_current_page must return False
            scroll_area=SimpleNamespace(
                parent=lambda: SimpleNamespace(width=lambda: 400),
                verticalScrollBar=lambda: SimpleNamespace(setValue=lambda v: None),
            ),
            _update_source_summary=lambda: None,
            _persist_session=lambda: None,
            _reset_pdf_scroll_position=lambda: None,
            _close_popover=lambda: None,
            _iter_unique_clean_words=lambda words: list(words),
            _clean_word=lambda t: t,
        )

        fake_page = SimpleNamespace(rect=SimpleNamespace(width=200))
        doc = SimpleNamespace(page_count=5, load_page=lambda _: fake_page)

        pdf_service = SimpleNamespace(
            doc=doc,
            render_page=lambda idx, zoom: SimpleNamespace(
                samples=b"\xff" * 60, width=20, height=10, stride=60,
                words=[], word_order=[], line_map={}, page_count=5,
            ),
            word_key=lambda w: str(w),
        )

        selection_state = window.selection
        mining_controller = SimpleNamespace(
            clear_selection=lambda: None,
            prefetch_translations=lambda *_: None,
        )

        controller = PDFController(window, pdf_service, selection_state, mining_controller)
        controller.current_page_index = 2
        controller.current_pdf_path = "book.pdf"
        return controller, activity_calls

    def test_next_page_records_activity(self):
        controller, calls = self._make_controller()

        with patch("immersion_app.gui.controllers.pdf_controller.QImage"), \
             patch("immersion_app.gui.controllers.pdf_controller.QPainter"), \
             patch("immersion_app.gui.controllers.pdf_controller.QPixmap"):
            controller.next_page()

        self.assertEqual(controller.current_page_index, 3)
        self.assertEqual(len(calls), 1, "next_page() should call record_activity() once")

    def test_prev_page_records_activity(self):
        controller, calls = self._make_controller()

        with patch("immersion_app.gui.controllers.pdf_controller.QImage"), \
             patch("immersion_app.gui.controllers.pdf_controller.QPainter"), \
             patch("immersion_app.gui.controllers.pdf_controller.QPixmap"):
            controller.prev_page()

        self.assertEqual(controller.current_page_index, 1)
        self.assertEqual(len(calls), 1, "prev_page() should call record_activity() once")

    def test_jump_to_page_records_activity(self):
        controller, calls = self._make_controller()

        with patch("immersion_app.gui.controllers.pdf_controller.QImage"), \
             patch("immersion_app.gui.controllers.pdf_controller.QPainter"), \
             patch("immersion_app.gui.controllers.pdf_controller.QPixmap"):
            controller.jump_to_page(5)

        self.assertEqual(controller.current_page_index, 4)
        self.assertEqual(len(calls), 1, "jump_to_page() should call record_activity() once")

    def test_next_page_at_last_page_does_not_record_activity(self):
        controller, calls = self._make_controller()
        controller.current_page_index = 4  # already at last page

        controller.next_page()

        self.assertEqual(len(calls), 0, "next_page() at last page should not call record_activity()")

    def test_prev_page_at_first_page_does_not_record_activity(self):
        controller, calls = self._make_controller()
        controller.current_page_index = 0  # already at first page

        controller.prev_page()

        self.assertEqual(len(calls), 0, "prev_page() at first page should not call record_activity()")


if __name__ == "__main__":
    unittest.main()
