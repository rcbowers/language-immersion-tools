#!/usr/bin/env python3
"""Regression tests for subtitle hit-testing and unified selection helpers."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QTextEdit

from immersion_app.gui.main_window import UnifiedSentenceMinerWindow
from immersion_app.gui.widgets.subtitle_widget import ClickableSubtitleLabel
from immersion_app.media.subtitle_parser import SRTParser


class SubtitleWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_widget(self, subtitle, width=480, height=120):
        widget = ClickableSubtitleLabel()
        widget.resize(width, height)
        widget.set_subtitle(subtitle)
        widget.show()
        self.app.processEvents()
        widget._ensure_layout()
        return widget

    def _click_center_for_word(self, widget, word_index):
        rects = widget._word_rects[word_index]
        self.assertTrue(rects)
        return rects[0].center()

    def _line_for_word(self, widget, word):
        for line_index in range(widget._layout.lineCount()):
            line = widget._layout.lineAt(line_index)
            line_start = line.textStart()
            line_end = line_start + line.textLength()
            if max(word.start, line_start) < min(word.end, line_end):
                return line
        self.fail(f"no layout line found for word {word.word!r}")

    def test_hit_testing_single_line(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola mundo cruel").subtitles[0]
        widget = self._make_widget(subtitle, width=520, height=100)
        for index, word in enumerate(subtitle.words):
            center = self._click_center_for_word(widget, index)
            self.assertEqual(widget._word_at_position(center), (word.word, index))

    def test_hit_testing_wrapped_lines(self):
        subtitle = SRTParser.from_text(
            "1\n00:00:00,000 --> 00:00:02,000\nuno dos tres cuatro cinco seis siete ocho nueve diez"
        ).subtitles[0]
        widget = self._make_widget(subtitle, width=180, height=140)
        line_tops = {round(rects[0].top(), 2) for rects in widget._word_rects if rects}
        self.assertGreater(len(line_tops), 1)
        for index, word in enumerate(subtitle.words):
            center = self._click_center_for_word(widget, index)
            self.assertEqual(widget._word_at_position(center), (word.word, index))

    def test_highlight_range_uses_parsed_word_indices(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola, mundo cruel").subtitles[0]
        widget = self._make_widget(subtitle, width=420, height=100)
        widget.highlight_word_range(0, 1)
        self.assertEqual(widget._highlighted_indices, {0, 1})
        self.assertEqual([word.word for word in subtitle.words[:2]], ["hola", "mundo"])

    def test_hit_testing_respects_margins(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola mundo").subtitles[0]
        widget = self._make_widget(subtitle, width=400, height=100)
        self.assertIsNone(widget._word_at_position(QPointF(5.0, 5.0)))
        self.assertIsNone(widget._word_at_position(QPointF(0.0, 0.0)))

    def test_single_line_word_rects_match_qtextlayout_positions(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nuno dos tres pero cinco").subtitles[0]
        widget = self._make_widget(subtitle, width=700, height=100)
        target_word = subtitle.words[3]
        target_rect = widget._word_rects[3][0]
        line = self._line_for_word(widget, target_word)
        start_x = widget._cursor_x(line, target_word.start)
        end_x = widget._cursor_x(line, target_word.end)
        self.assertAlmostEqual(target_rect.left(), min(start_x, end_x), places=2)
        self.assertAlmostEqual(target_rect.width(), abs(end_x - start_x), places=2)

    def test_selection_anchor_rect_spans_first_visual_line(self):
        subtitle = SRTParser.from_text(
            "1\n00:00:00,000 --> 00:00:02,000\nuno dos tres cuatro cinco seis siete ocho nueve diez"
        ).subtitles[0]
        widget = self._make_widget(subtitle, width=180, height=140)
        anchor = widget.selection_anchor_rect(0, 4)
        first_rect = widget._word_rects[0][0]
        self.assertFalse(anchor.isNull())
        self.assertEqual(anchor.top(), int(first_rect.top()))
        self.assertLessEqual(anchor.left(), int(first_rect.left()))


class UnifiedSelectionTests(unittest.TestCase):
    def _make_selection_stub(self):
        class _Stub:
            pass

        stub = _Stub()
        stub.word_value = QLineEdit()
        stub.sentence_value = QTextEdit()
        stub.translation_value = QTextEdit()
        stub.add_now_button = QPushButton()
        stub.add_queue_button = QPushButton()
        stub.source_header_label = QLabel()
        stub.selected_word = ""
        stub.selected_sentence = ""
        stub.selected_translation = ""
        stub.current_source_name = ""
        stub.current_source_location = ""
        stub.selected_subtitle_indices = []
        stub.selected_pdf_words = []
        stub.translation_popover = type("_Popover", (), {"isVisible": lambda self: False, "close": lambda self: None})()
        stub._close_popover = lambda: None
        return stub

    def _make_add_stub(self):
        window = self._make_selection_stub()
        window.selected_word = "hola"
        window.selected_sentence = "hola mundo"
        window.selected_translation = "hello"
        window.current_source_type = "video"
        window.current_source_name = "clip.mp4"
        window.current_source_location = "00:01"
        window.is_anki_connected = True
        window.sentence_counts = {}
        window.status_messages = []
        window.queued_refreshes = 0
        window.recorded_words = []
        window._set_status = lambda message, timeout_ms=4000: window.status_messages.append(message)
        window._refresh_queue_summary = lambda: setattr(window, "queued_refreshes", window.queued_refreshes + 1)
        window._record_successful_card_add = window.recorded_words.append
        window._queue_payload = UnifiedSentenceMinerWindow._queue_payload.__get__(window, UnifiedSentenceMinerWindow)
        window._build_note_sentence = UnifiedSentenceMinerWindow._build_note_sentence.__get__(
            window, UnifiedSentenceMinerWindow
        )
        window._queue_current_selection_for_later = UnifiedSentenceMinerWindow._queue_current_selection_for_later.__get__(
            window, UnifiedSentenceMinerWindow
        )
        return window

    def test_subtitle_click_uses_parsed_words(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola, mundo cruel.").subtitles[0]
        window = UnifiedSentenceMinerWindow.__new__(UnifiedSentenceMinerWindow)
        window.current_subtitle = subtitle
        window.subtitle_selection_anchor = None
        window.selected_word = ""
        window.selected_sentence = ""
        window.selected_translation = ""
        window.current_source_type = "video"
        window.current_source_location = "00:00"
        window.selected_subtitle_indices = []
        window.selected_pdf_words = []
        window._clean_word = lambda value: value.strip()
        window._update_selection_panel = lambda: None
        window._update_action_buttons = lambda: None
        window._requested_translation = None
        window._request_translation = lambda text: setattr(window, "_requested_translation", text)
        window.media_player = type("_Player", (), {"position": lambda self: 0})()

        class _StubLabel:
            def __init__(self):
                self.ranges = []

            def highlight_word_range(self, start, end):
                self.ranges.append((start, end))

        window.subtitle_label = _StubLabel()
        window._resolve_selected_subtitle_indices = UnifiedSentenceMinerWindow._resolve_selected_subtitle_indices.__get__(
            window, UnifiedSentenceMinerWindow
        )
        window._fmt_ms = UnifiedSentenceMinerWindow._fmt_ms.__get__(window, UnifiedSentenceMinerWindow)

        UnifiedSentenceMinerWindow._on_subtitle_click(window, "hola", 0, Qt.KeyboardModifier.NoModifier)

        self.assertEqual(window.selected_word, "hola")
        self.assertEqual(window.selected_sentence, subtitle.text)
        self.assertEqual(window._requested_translation, "hola")
        self.assertEqual(window.subtitle_label.ranges, [(0, 0)])

    def test_manual_word_input_requests_translation_on_submit(self):
        window = self._make_selection_stub()
        requested = []
        window._request_translation = requested.append
        window._update_selection_panel = lambda: UnifiedSentenceMinerWindow._update_selection_panel(window)
        window._update_action_buttons = lambda: UnifiedSentenceMinerWindow._update_action_buttons(window)
        window.word_value.setText("por si acaso")
        UnifiedSentenceMinerWindow._translate_word_field_input(window)
        self.assertEqual(window.selected_word, "por si acaso")
        self.assertEqual(requested, ["por si acaso"])

    def test_manual_word_input_ignores_empty_submit(self):
        window = self._make_selection_stub()
        requested = []
        window.selected_word = "hola"
        window.selected_translation = "hello"
        window._request_translation = requested.append
        window._update_selection_panel = lambda: UnifiedSentenceMinerWindow._update_selection_panel(window)
        window._update_action_buttons = lambda: UnifiedSentenceMinerWindow._update_action_buttons(window)
        window.word_value.setText("   ")
        UnifiedSentenceMinerWindow._translate_word_field_input(window)
        self.assertEqual(window.selected_word, "")
        self.assertEqual(window.selected_translation, "")
        self.assertEqual(requested, [])

    def test_manual_translation_enables_card_actions_without_context(self):
        window = self._make_selection_stub()
        window.selected_word = "por si acaso"
        window.selected_sentence = ""
        window.selected_translation = "just in case"
        UnifiedSentenceMinerWindow._update_action_buttons(window)
        self.assertTrue(window.add_now_button.isEnabled())
        self.assertTrue(window.add_queue_button.isEnabled())

    def test_add_now_adds_directly_when_anki_connected(self):
        window = self._make_add_stub()
        with (
            patch("immersion_app.gui.main_window.add_anki_card", return_value=1234) as add_card,
            patch("immersion_app.gui.main_window.append_queue_entry") as append_queue,
        ):
            UnifiedSentenceMinerWindow._add_now(window)

        add_card.assert_called_once_with("hola mundo", "hola", "hello")
        append_queue.assert_not_called()
        self.assertEqual(window.recorded_words, ["hola"])
        self.assertEqual(window.queued_refreshes, 0)
        self.assertIn("Added card to Anki (Note ID: 1234)", window.status_messages)

    def test_add_now_queues_when_anki_precheck_is_disconnected(self):
        window = self._make_add_stub()
        window.is_anki_connected = False
        with (
            patch("immersion_app.gui.main_window.append_queue_entry") as append_queue,
            patch("immersion_app.gui.main_window.QMessageBox.information") as info_box,
            patch("immersion_app.gui.main_window.QMessageBox.critical") as critical_box,
            patch("immersion_app.gui.main_window.add_anki_card") as add_card,
        ):
            UnifiedSentenceMinerWindow._add_now(window)

        add_card.assert_not_called()
        append_queue.assert_called_once()
        queued_entry = append_queue.call_args.args[0]
        self.assertEqual(queued_entry["word"], "hola")
        self.assertEqual(queued_entry["translation"], "hello")
        self.assertEqual(window.recorded_words, [])
        self.assertEqual(window.queued_refreshes, 1)
        info_box.assert_called_once()
        critical_box.assert_not_called()

    def test_add_now_queues_when_connection_drops_during_add(self):
        window = self._make_add_stub()
        with (
            patch(
                "immersion_app.gui.main_window.add_anki_card",
                side_effect=ConnectionError("Failed to connect to AnkiConnect"),
            ) as add_card,
            patch("immersion_app.gui.main_window.append_queue_entry") as append_queue,
            patch("immersion_app.gui.main_window.QMessageBox.information") as info_box,
            patch("immersion_app.gui.main_window.QMessageBox.critical") as critical_box,
        ):
            UnifiedSentenceMinerWindow._add_now(window)

        add_card.assert_called_once_with("hola mundo", "hola", "hello")
        append_queue.assert_called_once()
        self.assertEqual(window.recorded_words, [])
        self.assertEqual(window.queued_refreshes, 1)
        info_box.assert_called_once()
        critical_box.assert_not_called()

    def test_add_now_keeps_non_connection_errors_visible(self):
        window = self._make_add_stub()
        with (
            patch("immersion_app.gui.main_window.add_anki_card", side_effect=RuntimeError("deck missing")) as add_card,
            patch("immersion_app.gui.main_window.append_queue_entry") as append_queue,
            patch("immersion_app.gui.main_window.QMessageBox.information") as info_box,
            patch("immersion_app.gui.main_window.QMessageBox.critical") as critical_box,
        ):
            UnifiedSentenceMinerWindow._add_now(window)

        add_card.assert_called_once_with("hola mundo", "hola", "hello")
        append_queue.assert_not_called()
        info_box.assert_not_called()
        critical_box.assert_called_once()
        self.assertEqual(window.recorded_words, [])
        self.assertEqual(window.queued_refreshes, 0)


if __name__ == "__main__":
    unittest.main()
