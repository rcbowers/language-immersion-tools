#!/usr/bin/env python3
"""Regression tests for subtitle hit-testing and unified selection helpers."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QTextEdit

from immersion_app.core.anki_analytics import AnkiAnalyticsManager
from immersion_app.core.selection_state import SelectionState
from immersion_app.core.user_data import default_user_data
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
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

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
        stub.selection = SelectionState()
        stub.current_source_name = ""
        stub.current_source_location = ""
        stub.selected_subtitle_indices = []
        stub.selected_pdf_words = []
        stub.translation_popover = type("_Popover", (), {"isVisible": lambda self: False, "close": lambda self: None})()
        stub.mode_manager = type("_ModeManager", (), {"mode_string": lambda self: "video"})()
        stub._close_popover = lambda: None
        return stub

    def test_manual_translation_enables_card_actions_without_context(self):
        window = self._make_selection_stub()
        window.selection.word = "por si acaso"
        window.selection.sentence = ""
        window.selection.translation = "just in case"
        UnifiedSentenceMinerWindow._update_action_buttons(window)
        self.assertTrue(window.add_now_button.isEnabled())
        self.assertTrue(window.add_queue_button.isEnabled())


class AnkiStatsUpdateTests(unittest.TestCase):
    def _make_stats_stub(self):
        class _CommandBar:
            def __init__(self):
                self.stats_calls = []

            def set_stats(self, today_count, total_count):
                self.stats_calls.append((today_count, total_count))

        class _SubtitleLabel:
            def __init__(self):
                self.vocabulary_seen = []

            def set_vocabulary_seen(self, vocabulary_seen):
                self.vocabulary_seen.append(set(vocabulary_seen))

        window = UnifiedSentenceMinerWindow.__new__(UnifiedSentenceMinerWindow)
        window.user_data = default_user_data()
        window.anki_analytics = AnkiAnalyticsManager(window.user_data)
        window.analytics_vocabulary = set()
        window.command_bar = _CommandBar()
        window.subtitle_label = _SubtitleLabel()
        window.pdf_service = SimpleNamespace(doc=None)
        window.current_pdf_path = ""
        window._render_current_page = lambda: None
        window._refresh_word_highlights = UnifiedSentenceMinerWindow._refresh_word_highlights.__get__(
            window, UnifiedSentenceMinerWindow
        )
        window._on_anki_analytics_changed = UnifiedSentenceMinerWindow._on_anki_analytics_changed.__get__(
            window, UnifiedSentenceMinerWindow
        )
        window.anki_analytics.stats_changed.connect(window._on_anki_analytics_changed)
        return window

    def test_record_successful_card_add_updates_command_bar_today_count(self):
        window = self._make_stats_stub()

        with patch("immersion_app.core.anki_analytics.save_user_data"):
            UnifiedSentenceMinerWindow._record_successful_card_add(window, "hola")

        self.assertEqual(window.command_bar.stats_calls[-1], (1, 1))
        self.assertEqual(window.analytics_vocabulary, {"hola"})
        self.assertEqual(window.subtitle_label.vocabulary_seen[-1], {"hola"})

if __name__ == "__main__":
    unittest.main()
