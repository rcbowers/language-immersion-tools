#!/usr/bin/env python3
"""Regression tests for subtitle hit-testing and unified selection helpers."""

from datetime import datetime
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
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

    def _make_add_stub(self):
        window = self._make_selection_stub()
        window.selection.word = "hola"
        window.selection.sentence = "hola mundo"
        window.selection.translation = "hello"
        window.current_source_type = "video"
        window.current_source_name = "clip.mp4"
        window.current_source_location = "00:01"
        window.is_anki_connected = True
        window.sentence_counts = {}
        window.status_messages = []
        window.queued_refreshes = 0
        window.recorded_words = []
        window.feedback_events = []
        window._set_status = lambda message, timeout_ms=4000: window.status_messages.append(message)
        window._show_card_feedback = lambda title, sentence, variant, note_id=None, reason="": window.feedback_events.append(
            {
                "title": title,
                "sentence": sentence,
                "variant": variant,
                "note_id": note_id,
                "reason": reason,
            }
        )
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
        window.selection = SelectionState()
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

        self.assertEqual(window.selection.word, "hola")
        self.assertEqual(window.selection.sentence, subtitle.text)
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
        self.assertEqual(window.selection.word, "por si acaso")
        self.assertEqual(requested, ["por si acaso"])

    def test_manual_word_input_ignores_empty_submit(self):
        window = self._make_selection_stub()
        requested = []
        window.selection.word = "hola"
        window.selection.translation = "hello"
        window._request_translation = requested.append
        window._update_selection_panel = lambda: UnifiedSentenceMinerWindow._update_selection_panel(window)
        window._update_action_buttons = lambda: UnifiedSentenceMinerWindow._update_action_buttons(window)
        window.word_value.setText("   ")
        UnifiedSentenceMinerWindow._translate_word_field_input(window)
        self.assertEqual(window.selection.word, "")
        self.assertEqual(window.selection.translation, "")
        self.assertEqual(requested, [])

    def test_manual_translation_enables_card_actions_without_context(self):
        window = self._make_selection_stub()
        window.selection.word = "por si acaso"
        window.selection.sentence = ""
        window.selection.translation = "just in case"
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
        self.assertEqual(
            window.feedback_events,
            [
                {
                    "title": "Added to Anki",
                    "sentence": "hola mundo",
                    "variant": "added",
                    "note_id": 1234,
                    "reason": "",
                }
            ],
        )

    def test_add_now_queues_when_anki_precheck_is_disconnected(self):
        window = self._make_add_stub()
        window.is_anki_connected = False
        with (
            patch("immersion_app.gui.main_window.append_queue_entry") as append_queue,
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
        critical_box.assert_not_called()
        self.assertEqual(
            window.feedback_events,
            [
                {
                    "title": "Queued for later",
                    "sentence": "hola mundo",
                    "variant": "queued",
                    "note_id": None,
                    "reason": "AnkiConnect is not available",
                }
            ],
        )

    def test_add_now_queues_when_connection_drops_during_add(self):
        window = self._make_add_stub()
        with (
            patch(
                "immersion_app.gui.main_window.add_anki_card",
                side_effect=ConnectionError("Failed to connect to AnkiConnect"),
            ) as add_card,
            patch("immersion_app.gui.main_window.append_queue_entry") as append_queue,
            patch("immersion_app.gui.main_window.QMessageBox.critical") as critical_box,
        ):
            UnifiedSentenceMinerWindow._add_now(window)

        add_card.assert_called_once_with("hola mundo", "hola", "hello")
        append_queue.assert_called_once()
        self.assertEqual(window.recorded_words, [])
        self.assertEqual(window.queued_refreshes, 1)
        critical_box.assert_not_called()
        self.assertEqual(
            window.feedback_events,
            [
                {
                    "title": "Queued for later",
                    "sentence": "hola mundo",
                    "variant": "queued",
                    "note_id": None,
                    "reason": "Failed to connect to AnkiConnect",
                }
            ],
        )

    def test_add_now_keeps_non_connection_errors_visible(self):
        window = self._make_add_stub()
        with (
            patch("immersion_app.gui.main_window.add_anki_card", side_effect=RuntimeError("deck missing")) as add_card,
            patch("immersion_app.gui.main_window.append_queue_entry") as append_queue,
            patch("immersion_app.gui.main_window.QMessageBox.critical") as critical_box,
        ):
            UnifiedSentenceMinerWindow._add_now(window)

        add_card.assert_called_once_with("hola mundo", "hola", "hello")
        append_queue.assert_not_called()
        critical_box.assert_called_once()
        self.assertEqual(window.recorded_words, [])
        self.assertEqual(window.queued_refreshes, 0)
        self.assertEqual(window.feedback_events, [])

    def test_add_to_queue_shows_card_feedback(self):
        window = self._make_add_stub()
        with (
            patch("immersion_app.gui.main_window.append_queue_entry") as append_queue,
            patch("immersion_app.gui.main_window.QMessageBox.critical") as critical_box,
        ):
            UnifiedSentenceMinerWindow._add_to_queue(window)

        append_queue.assert_called_once()
        critical_box.assert_not_called()
        self.assertEqual(window.queued_refreshes, 1)
        self.assertEqual(
            window.feedback_events,
            [
                {
                    "title": "Saved to queue",
                    "sentence": "hola mundo",
                    "variant": "queued",
                    "note_id": None,
                    "reason": "",
                }
            ],
        )


class TranslationPrefetchTests(unittest.TestCase):
    def _make_translation_stub(self):
        window = UnifiedSentenceMinerWindow.__new__(UnifiedSentenceMinerWindow)
        window.learning_language = "es"
        window.native_language = "en"
        window.translation_mode = "online"
        window.translation_cache = {}
        window._translation_requests = {}
        window._translation_requests_by_key = {}
        window._translation_context_version = 0
        window.current_request_id = 0
        window._next_translation_request_id = 0
        window._online_backend = object()
        window._offline_backend = object()
        window._cache_hits = 0
        window._cache_misses = 0
        window.selection = SelectionState()
        window.started_tasks = []
        window.thread_pool = type("_Pool", (), {"start": lambda self, task: window.started_tasks.append(task)})()
        window._update_selection_panel = lambda: None
        window._update_action_buttons = lambda: None
        window._set_status = lambda message, timeout_ms=4000: None
        window._get_translation_language_codes = lambda: ("es", "en")
        window._clean_word = UnifiedSentenceMinerWindow._clean_word.__get__(window, UnifiedSentenceMinerWindow)
        window._translation_cache_key = UnifiedSentenceMinerWindow._translation_cache_key.__get__(
            window, UnifiedSentenceMinerWindow
        )
        window._start_translation_request = UnifiedSentenceMinerWindow._start_translation_request.__get__(
            window, UnifiedSentenceMinerWindow
        )
        window._request_translation = UnifiedSentenceMinerWindow._request_translation.__get__(
            window, UnifiedSentenceMinerWindow
        )
        window._prefetch_translations = UnifiedSentenceMinerWindow._prefetch_translations.__get__(
            window, UnifiedSentenceMinerWindow
        )
        window._iter_unique_clean_words = UnifiedSentenceMinerWindow._iter_unique_clean_words.__get__(
            window, UnifiedSentenceMinerWindow
        )
        window._on_translation_done = UnifiedSentenceMinerWindow._on_translation_done.__get__(
            window, UnifiedSentenceMinerWindow
        )
        window._on_translation_failed = UnifiedSentenceMinerWindow._on_translation_failed.__get__(
            window, UnifiedSentenceMinerWindow
        )
        return window

    def test_request_translation_uses_cached_value_without_starting_task(self):
        window = self._make_translation_stub()
        window.translation_cache[("es", "en", "hola")] = "hello"

        window._request_translation("hola")

        self.assertEqual(window.selection.translation, "hello")
        self.assertEqual(window.started_tasks, [])

    def test_prefetch_completion_populates_cache_without_overwriting_visible_translation(self):
        window = self._make_translation_stub()
        window.selection.translation = "keep me"

        window._prefetch_translations(["hola"])
        self.assertEqual(len(window.started_tasks), 1)

        window.mode_manager = type("_ModeManager", (), {"current_mode": None})()
        window._on_batch_translation_done(["hola"], ["hello"])

        self.assertEqual(window.translation_cache[("es", "en", "hola")], "hello")
        self.assertEqual(window.selection.translation, "keep me")

    def test_visible_request_starts_new_request_when_prefetch_is_batch_only(self):
        window = self._make_translation_stub()

        window._prefetch_translations(["hola"])
        self.assertEqual(len(window.started_tasks), 1)

        window._request_translation("hola")

        self.assertEqual(len(window.started_tasks), 2)
        self.assertEqual(window.current_request_id, 1)
        self.assertEqual(window.selection.translation, "translating...")
        self.assertTrue(window._translation_requests[1]["visible"])

        window._on_translation_done(1, "hola", "hello")

        self.assertEqual(window.selection.translation, "hello")
        self.assertEqual(window.translation_cache[("es", "en", "hola")], "hello")

    def test_prefetch_deduplicates_inflight_words(self):
        window = self._make_translation_stub()

        window._prefetch_translations(["hola", "hola"])

        self.assertEqual(len(window.started_tasks), 1)


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
        window.doc = None
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

    def test_process_queue_updates_command_bar_today_count_per_successful_entry(self):
        window = self._make_stats_stub()
        window.is_anki_connected = True
        window.sentence_counts = {}
        window._refresh_queue_summary = lambda: None
        window._record_successful_card_add = UnifiedSentenceMinerWindow._record_successful_card_add.__get__(
            window, UnifiedSentenceMinerWindow
        )

        entries = [
            {
                "sentence": "hola mundo",
                "word": "hola",
                "translation": "hello",
                "created_at": datetime(2026, 5, 11, 8, 0).isoformat(timespec="seconds"),
            },
            {
                "sentence": "adios mundo",
                "word": "adios",
                "translation": "goodbye",
                "created_at": datetime(2026, 5, 11, 8, 5).isoformat(timespec="seconds"),
            },
        ]

        with (
            patch("immersion_app.gui.main_window.load_queue_entries", return_value=entries),
            patch("immersion_app.gui.main_window.save_queue_entries") as save_queue_entries,
            patch("immersion_app.gui.main_window.append_processed_log") as append_processed_log,
            patch("immersion_app.gui.main_window.add_anki_card"),
            patch("immersion_app.gui.main_window.QMessageBox.information"),
            patch("immersion_app.core.anki_analytics.save_user_data"),
        ):
            UnifiedSentenceMinerWindow._process_queue(window)

        self.assertEqual(window.command_bar.stats_calls[-1], (2, 2))
        self.assertEqual(window.analytics_vocabulary, {"hola", "adios"})
        append_processed_log.assert_called_once_with(entries)
        save_queue_entries.assert_called_once_with([])


if __name__ == "__main__":
    unittest.main()
