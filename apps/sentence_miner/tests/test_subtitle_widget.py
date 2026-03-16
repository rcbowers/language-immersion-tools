#!/usr/bin/env python3
"""Regression tests for subtitle hit-testing and selection."""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QTextEdit, QWidget

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from base_miner_window import AbstractSentenceMinerWindow
from subtitle_parser import SRTParser
from subtitle_widget import ClickableSubtitleLabel
from video_miner_window import VideoSentenceMinerWindow


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
        self.assertTrue(rects, f"word index {word_index} did not receive a hit-test rect")
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

        line_tops = {
            round(rects[0].top(), 2)
            for rects in widget._word_rects
            if rects
        }
        self.assertGreater(len(line_tops), 1)

        for index, word in enumerate(subtitle.words):
            center = self._click_center_for_word(widget, index)
            self.assertEqual(widget._word_at_position(center), (word.word, index))

    def test_hit_testing_after_font_change(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola mundo cruel").subtitles[0]
        widget = self._make_widget(subtitle, width=520, height=100)

        original_center = self._click_center_for_word(widget, 1)
        self.assertEqual(widget._word_at_position(original_center), ("mundo", 1))

        font = widget.font()
        next_size = font.pointSizeF() if font.pointSizeF() > 0 else 10.0
        font.setPointSizeF(next_size + 6.0)
        widget.setFont(font)
        self.app.processEvents()
        widget._ensure_layout()

        resized_center = self._click_center_for_word(widget, 1)
        self.assertEqual(widget._word_at_position(resized_center), ("mundo", 1))

    def test_highlight_range_uses_parsed_word_indices(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola, mundo cruel").subtitles[0]
        widget = self._make_widget(subtitle, width=420, height=100)

        widget.highlight_word_range(0, 1)

        self.assertEqual(widget._highlighted_indices, {0, 1})
        self.assertEqual([word.word for word in subtitle.words[:2]], ["hola", "mundo"])

    def test_long_subtitle_shrinks_to_fit_fixed_height(self):
        subtitle = SRTParser.from_text(
            "1\n00:00:00,000 --> 00:00:02,000\n"
            "uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis"
        ).subtitles[0]
        widget = self._make_widget(subtitle, width=180, height=96)

        self.assertLess(widget._fitted_point_size, widget._display_font().pointSizeF())
        self.assertLessEqual(widget._layout_total_height, widget.contentsRect().height())

    def test_short_subtitle_keeps_preferred_font_size(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola mundo").subtitles[0]
        widget = self._make_widget(subtitle, width=420, height=96)

        self.assertAlmostEqual(widget._fitted_point_size, widget._display_font().pointSizeF(), places=2)

    def test_hit_testing_uses_fitted_layout(self):
        subtitle = SRTParser.from_text(
            "1\n00:00:00,000 --> 00:00:02,000\n"
            "uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece"
        ).subtitles[0]
        widget = self._make_widget(subtitle, width=170, height=96)

        self.assertLess(widget._fitted_point_size, widget._display_font().pointSizeF())
        for index, word in enumerate(subtitle.words):
            center = self._click_center_for_word(widget, index)
            self.assertEqual(widget._word_at_position(center), (word.word, index))

    def test_font_change_recomputes_fitted_layout(self):
        subtitle = SRTParser.from_text(
            "1\n00:00:00,000 --> 00:00:02,000\n"
            "uno dos tres cuatro cinco seis siete ocho nueve diez once doce"
        ).subtitles[0]
        widget = self._make_widget(subtitle, width=180, height=96)

        font = widget.font()
        next_size = font.pointSizeF() if font.pointSizeF() > 0 else 10.0
        font.setPointSizeF(next_size + 8.0)
        widget.setFont(font)
        self.app.processEvents()
        widget._ensure_layout()

        self.assertLessEqual(widget._layout_total_height, widget.contentsRect().height())
        self.assertLessEqual(widget._fitted_point_size, widget._display_font().pointSizeF())
        self.assertGreaterEqual(widget._fitted_point_size, widget._minimum_subtitle_point_size)
        self.assertNotEqual(widget._fitted_point_size, 0.0)
        self.assertTrue(widget._word_rects)

    def test_hit_testing_with_explicit_coordinates(self):
        """Test that hit testing uses widget coordinates directly."""
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola mundo").subtitles[0]
        widget = self._make_widget(subtitle, width=400, height=100)

        # Get the actual rectangle for the first word
        rects = widget._word_rects[0]
        self.assertTrue(rects, "First word should have hit test rects")

        first_rect = rects[0]

        # Test that the rect is in widget space (should include margins)
        # With 10px margins, text should not start at (0,0)
        self.assertGreater(first_rect.left(), 5, "Rect should be offset by margins")
        self.assertGreater(first_rect.top(), 5, "Rect should be offset by margins")

        # Test hit detection at the rect's position directly
        test_point = first_rect.center()
        result = widget._word_at_position(test_point)
        self.assertEqual(result, ("hola", 0),
                         f"Click at rect center {test_point} should hit first word")

        # Test that clicking at the actual rect coordinates works
        click_x = first_rect.left() + 5
        click_y = first_rect.top() + 5
        result = widget._word_at_position(QPointF(click_x, click_y))
        self.assertEqual(result, ("hola", 0),
                         f"Click at ({click_x}, {click_y}) should hit first word")

    def test_hit_testing_respects_margins(self):
        """Test that hit testing works correctly with content margins."""
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola mundo").subtitles[0]
        widget = self._make_widget(subtitle, width=400, height=100)

        # Clicking in the margin area (top-left corner) should not hit any word
        margin_click = QPointF(5.0, 5.0)
        result = widget._word_at_position(margin_click)
        self.assertIsNone(result, "Click in margin area should not hit any word")

        # Clicking at (0,0) should also miss
        origin_click = QPointF(0.0, 0.0)
        result = widget._word_at_position(origin_click)
        self.assertIsNone(result, "Click at origin should not hit any word")

    def test_word_rects_in_widget_coordinate_space(self):
        """Verify that word rectangles are stored in widget coordinate space."""
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola mundo cruel").subtitles[0]
        widget = self._make_widget(subtitle, width=400, height=100)

        content_rect = widget._content_rect()

        for word_index, rects in enumerate(widget._word_rects):
            for rect in rects:
                # Rectangles should include margin offsets
                self.assertGreaterEqual(rect.left(), content_rect.left() - 1,
                                       f"Word {word_index} rect should be at or after content left edge")
                self.assertGreaterEqual(rect.top(), content_rect.top() - 1,
                                       f"Word {word_index} rect should be at or after content top edge")

                # Rectangles should be within widget bounds
                self.assertLessEqual(rect.right(), widget.width(),
                                    f"Word {word_index} rect should be within widget width")
                self.assertLessEqual(rect.bottom(), widget.height(),
                                    f"Word {word_index} rect should be within widget height")

    def test_single_line_word_rects_match_qtextlayout_positions(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nuno dos tres pero cinco").subtitles[0]
        widget = self._make_widget(subtitle, width=700, height=100)

        target_index = 3
        target_word = subtitle.words[target_index]
        target_rect = widget._word_rects[target_index][0]
        line = self._line_for_word(widget, target_word)

        start_x = widget._cursor_x(line, target_word.start)
        end_x = widget._cursor_x(line, target_word.end)

        self.assertAlmostEqual(target_rect.left(), min(start_x, end_x), places=2)
        self.assertAlmostEqual(target_rect.width(), abs(end_x - start_x), places=2)
        self.assertLessEqual(target_rect.right(), widget.contentsRect().right() + 1.0)

    def test_coordinate_system_validation(self):
        """Test the internal coordinate system validation."""
        subtitle = SRTParser.from_text(
            "1\n00:00:00,000 --> 00:00:02,000\nuno dos tres cuatro cinco"
        ).subtitles[0]
        widget = self._make_widget(subtitle, width=300, height=100)

        # Coordinate system should be valid
        self.assertTrue(widget._validate_coordinate_system(),
                       "Coordinate system should be internally consistent")

    def test_get_word_debug_bounds_matches_hit_test_rects(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola mundo cruel").subtitles[0]
        widget = self._make_widget(subtitle, width=420, height=100)

        debug_bounds = widget.get_word_debug_bounds()

        self.assertEqual(len(debug_bounds), len(subtitle.words))
        self.assertEqual(debug_bounds[1]["word"], "mundo")
        self.assertEqual(len(debug_bounds[1]["rects"]), len(widget._word_rects[1]))
        self.assertAlmostEqual(debug_bounds[1]["rects"][0]["x"], widget._word_rects[1][0].x(), places=2)
        self.assertAlmostEqual(debug_bounds[1]["rects"][0]["width"], widget._word_rects[1][0].width(), places=2)

    def test_debug_click_reports_hit_and_miss(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola mundo").subtitles[0]
        widget = self._make_widget(subtitle, width=400, height=100)
        payloads = []
        widget.debug_clicked.connect(payloads.append)

        hit_point = self._click_center_for_word(widget, 0)
        miss_point = QPointF(2.0, 2.0)

        widget.debug_clicked.emit(
            {
                "x": float(hit_point.x()),
                "y": float(hit_point.y()),
                "word": "hola",
                "index": 0,
            }
        )
        widget.debug_clicked.emit(
            {
                "x": float(miss_point.x()),
                "y": float(miss_point.y()),
                "word": None,
                "index": None,
            }
        )

        self.assertEqual(payloads[0]["word"], "hola")
        self.assertEqual(payloads[0]["index"], 0)
        self.assertIsNone(payloads[1]["word"])
        self.assertIsNone(payloads[1]["index"])


class VideoSubtitleSelectionTests(unittest.TestCase):
    def _make_selection_stub(self):
        class _Stub:
            pass

        stub = _Stub()
        stub.word_value = QLineEdit()
        stub.sentence_value = QTextEdit()
        stub.translation_value = QTextEdit()
        stub.add_now_button = QPushButton()
        stub.add_queue_button = QPushButton()
        stub.selected_word = ""
        stub.selected_sentence = ""
        stub.selected_translation = ""
        return stub

    def test_video_window_uses_parsed_subtitle_words(self):
        subtitle = SRTParser.from_text("1\n00:00:00,000 --> 00:00:02,000\nhola, mundo cruel.").subtitles[0]

        window = VideoSentenceMinerWindow.__new__(VideoSentenceMinerWindow)
        window.current_subtitle = subtitle
        window.subtitle_selection_anchor = None
        window.selected_word = ""
        window.selected_sentence = ""
        window.selected_translation = ""
        window._clean_word = lambda value: value.strip()
        window._update_selection_panel = lambda: None
        window._update_action_buttons = lambda: None
        window._requested_translation = None
        window._request_translation = lambda text: setattr(window, "_requested_translation", text)

        class _StubLabel:
            def __init__(self):
                self.ranges = []

            def highlight_word_range(self, start, end):
                self.ranges.append((start, end))

        window.subtitle_label = _StubLabel()
        window._resolve_selected_subtitle_indices = VideoSentenceMinerWindow._resolve_selected_subtitle_indices.__get__(
            window, VideoSentenceMinerWindow
        )

        VideoSentenceMinerWindow._on_subtitle_click(window, "hola", 0, Qt.KeyboardModifier.NoModifier)

        self.assertEqual(window.selected_word, "hola")
        self.assertEqual(window.selected_sentence, subtitle.text)
        self.assertEqual(window._requested_translation, "hola")
        self.assertEqual(window.subtitle_label.ranges, [(0, 0)])

    def test_manual_word_input_requests_translation_on_submit(self):
        window = self._make_selection_stub()
        requested = []
        window._request_translation = requested.append
        window._update_selection_panel = lambda: AbstractSentenceMinerWindow._update_selection_panel(window)
        window._update_action_buttons = lambda: AbstractSentenceMinerWindow._update_action_buttons(window)

        window.word_value.setText("por si acaso")

        AbstractSentenceMinerWindow._translate_word_field_input(window)

        self.assertEqual(window.selected_word, "por si acaso")
        self.assertEqual(window.selected_translation, "Translating...")
        self.assertEqual(window.word_value.text(), "por si acaso")
        self.assertEqual(requested, ["por si acaso"])

    def test_manual_word_input_ignores_empty_submit(self):
        window = self._make_selection_stub()
        requested = []
        window.selected_word = "hola"
        window.selected_translation = "hello"
        window.word_value.setText("   ")
        window._request_translation = requested.append
        window._update_selection_panel = lambda: AbstractSentenceMinerWindow._update_selection_panel(window)
        window._update_action_buttons = lambda: AbstractSentenceMinerWindow._update_action_buttons(window)

        AbstractSentenceMinerWindow._translate_word_field_input(window)

        self.assertEqual(window.selected_word, "")
        self.assertEqual(window.selected_translation, "")
        self.assertEqual(window.word_value.text(), "")
        self.assertEqual(requested, [])

    def test_manual_translation_enables_card_actions_without_context(self):
        window = self._make_selection_stub()
        window.selected_word = "por si acaso"
        window.selected_sentence = ""
        window.selected_translation = "just in case"

        AbstractSentenceMinerWindow._update_action_buttons(window)

        self.assertTrue(window.add_now_button.isEnabled())
        self.assertTrue(window.add_queue_button.isEnabled())

    def test_video_window_time_label_width_uses_longest_duration_format(self):
        window = VideoSentenceMinerWindow.__new__(VideoSentenceMinerWindow)
        window.time_label = QLabel()
        window._time_label_sample_text = VideoSentenceMinerWindow._time_label_sample_text.__get__(
            window, VideoSentenceMinerWindow
        )

        VideoSentenceMinerWindow._update_time_label_width(window, 4_200_000)

        expected = window.time_label.fontMetrics().horizontalAdvance("00:00:00 / 00:00:00") + 10
        self.assertEqual(window.time_label.width(), expected)
        self.assertEqual(window.time_label.minimumWidth(), expected)
        self.assertEqual(window.time_label.maximumWidth(), expected)

    def test_video_window_focus_helper_clears_word_field_focus(self):
        host = QWidget()
        layout = QVBoxLayout(host)
        word_value = QLineEdit()
        video_container = QWidget()
        video_container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(word_value)
        layout.addWidget(video_container)
        host.show()
        self.app.processEvents()

        word_value.setFocus()
        self.app.processEvents()
        self.assertTrue(word_value.hasFocus())

        window = VideoSentenceMinerWindow.__new__(VideoSentenceMinerWindow)
        window.word_value = word_value
        window.video_container = video_container
        window.video_widget = None

        VideoSentenceMinerWindow._focus_video_playback_surface(window)
        self.app.processEvents()

        self.assertFalse(word_value.hasFocus())
        self.assertTrue(video_container.hasFocus())

    def test_transport_overlay_positions_inside_video_container(self):
        window = VideoSentenceMinerWindow.__new__(VideoSentenceMinerWindow)
        window.video_container = QWidget()
        window.video_container.resize(800, 500)
        window.transport_overlay = QWidget(window.video_container)
        window.transport_overlay.setLayout(QHBoxLayout())
        window.transport_overlay.layout().addWidget(QPushButton("Play"))
        window.transport_overlay.layout().addWidget(QSlider(Qt.Orientation.Horizontal))
        window.transport_overlay.layout().addWidget(QLabel("00:00 / 00:00"))

        VideoSentenceMinerWindow._position_transport_overlay(window)

        geometry = window.transport_overlay.geometry()
        self.assertGreaterEqual(geometry.x(), 16)
        self.assertGreaterEqual(geometry.y(), 16)
        self.assertLessEqual(geometry.right(), window.video_container.width())
        self.assertLessEqual(geometry.bottom(), window.video_container.height())

    def test_transport_overlay_hides_when_idle(self):
        window = VideoSentenceMinerWindow.__new__(VideoSentenceMinerWindow)
        window.transport_overlay = QWidget()
        window.transport_overlay.show()
        window.video_container = QWidget()
        window.video_widget = QWidget()
        window.play_pause_button = QPushButton()
        window.position_slider = QSlider(Qt.Orientation.Horizontal)
        window.time_label = QLabel()
        window._is_slider_dragging = False
        window._transport_hide_timer = QTimer()

        VideoSentenceMinerWindow._hide_transport_overlay_if_idle(window)

        self.assertFalse(window.transport_overlay.isVisible())


if __name__ == "__main__":
    unittest.main()
