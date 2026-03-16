#!/usr/bin/env python3
"""Clickable subtitle overlay widget."""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QTextCharFormat, QTextLayout, QTextOption
from PySide6.QtWidgets import QLabel

"""
COORDINATE SYSTEM OVERVIEW:

This widget uses Qt's QTextLayout for advanced text rendering with proper wrapping,
centering, and highlighting. Understanding the coordinate system is crucial:

1. Widget Coordinate Space:
   - Origin (0,0) is at the top-left corner of the widget
   - Mouse events report positions in this space
   - Drawing operations use this space

2. Content Rectangle:
   - Inset by margins (default 10px on all sides via setContentsMargins)
   - Used to position text within the widget with padding
   - content_rect.left() = 10, content_rect.top() = 10 (with default margins)

3. QTextLayout Positioning:
   - Lines are positioned using line.setPosition()
   - These positions include content_rect offsets for proper centering
   - When drawing with layout.draw(painter, QPointF(0,0)), lines appear at
     their stored positions relative to the widget origin

4. Word Rectangles (_word_rects):
   - Stored in WIDGET COORDINATE SPACE
   - QTextLine.cursorToX() already reports x positions in the same layout space used
     during painting, including the line's horizontal placement
   - Therefore rectangles can be directly compared with mouse event positions

Hit Testing:
   - Mouse click at widget (150, 50) should be compared directly with
     word rect at (150, 50) - no transformation needed
   - The content_rect margins are already baked into the word rect positions

This design ensures that:
   - Text rendering and layout are handled by Qt's robust QTextLayout
   - Word rectangles match the visual layout precisely
   - Hit testing is a simple point-in-rect check without coordinate transforms
"""


class ClickableSubtitleLabel(QLabel):
    clicked = Signal(str, int, object)
    debug_clicked = Signal(object)
    layout_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._subtitle = None
        self._raw_text = ""
        self._words = []
        self._highlighted_indices = set()
        self._layout = None
        self._word_rects = []
        self._layout_dirty = True
        self._preferred_subtitle_point_size = 20.0
        self._minimum_subtitle_point_size = 7.0
        self._layout_total_height = 0.0
        self._fitted_point_size = 0.0

        self.setContentsMargins(10, 10, 10, 10)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_subtitle(self, subtitle):
        self._subtitle = subtitle
        self._raw_text = subtitle.text if subtitle else ""
        self._words = list(subtitle.words) if subtitle else []
        self._highlighted_indices = set()
        self._invalidate_layout()
        self._notify_layout_updated()

    def set_subtitle_text(self, text):
        subtitle = None if not text else type("_SubtitleText", (), {"text": text, "words": []})()
        self.set_subtitle(subtitle)

    def highlight_word_range(self, start_index, end_index):
        if not self._words or start_index is None or end_index is None:
            self._highlighted_indices = set()
            self.update()
            return

        start = max(0, min(start_index, end_index))
        end = min(len(self._words) - 1, max(start_index, end_index))
        self._highlighted_indices = set(range(start, end + 1))
        self._invalidate_layout(update_widget=False)
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._words:
            super().mousePressEvent(event)
            return

        click_point = event.position()
        word_info = self._word_at_position(click_point)
        self.debug_clicked.emit(
            {
                "x": float(click_point.x()),
                "y": float(click_point.y()),
                "word": word_info[0] if word_info else None,
                "index": word_info[1] if word_info else None,
            }
        )
        if word_info:
            word, index = word_info
            self.clicked.emit(word, index, event.modifiers())
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        self._invalidate_layout(update_widget=False)
        self._notify_layout_updated()
        super().resizeEvent(event)

    def changeEvent(self, event):
        if event.type() in (
            event.Type.FontChange,
            event.Type.StyleChange,
            event.Type.PaletteChange,
        ):
            self._invalidate_layout(update_widget=False)
            self._notify_layout_updated()
        super().changeEvent(event)

    def paintEvent(self, event):
        if not self._raw_text:
            return

        self._ensure_layout()
        if self._layout is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(self.rect().adjusted(0, 0, -1, -1)), 6, 6)
        self._layout.draw(painter, QPointF(0.0, 0.0))

    def _display_font(self):
        font = self.font()
        size = font.pointSizeF()
        if size <= 0:
            size = 10.0
        font.setPointSizeF(max(self._preferred_subtitle_point_size, size))
        font.setBold(True)
        return font

    def _invalidate_layout(self, update_widget=True):
        self._layout = None
        self._word_rects = []
        self._layout_dirty = True
        self._layout_total_height = 0.0
        self._fitted_point_size = 0.0
        if update_widget:
            self.update()

    def _content_rect(self):
        return QRectF(self.contentsRect())

    def get_word_debug_bounds(self):
        self._ensure_layout()
        bounds = []
        for index, word in enumerate(self._words):
            rects = []
            for rect in self._word_rects[index]:
                rects.append(
                    {
                        "x": float(rect.x()),
                        "y": float(rect.y()),
                        "width": float(rect.width()),
                        "height": float(rect.height()),
                    }
                )
            bounds.append({"index": index, "word": word.word, "rects": rects})
        return bounds

    def _notify_layout_updated(self):
        self._ensure_layout()
        self.layout_updated.emit()

    def _ensure_layout(self):
        if not self._layout_dirty:
            return

        self._layout_dirty = False
        self._layout = None
        self._word_rects = [[] for _ in self._words]
        self._layout_total_height = 0.0
        self._fitted_point_size = 0.0
        if not self._raw_text:
            return

        content_rect = self._content_rect()
        if content_rect.width() <= 1 or content_rect.height() <= 1:
            return

        preferred_font = self._display_font()
        preferred_size = preferred_font.pointSizeF()
        minimum_size = min(self._minimum_subtitle_point_size, preferred_size)

        layout = None
        lines = []
        total_height = 0.0
        chosen_size = minimum_size

        candidate_size = preferred_size
        while candidate_size >= minimum_size - 0.001:
            candidate_font = preferred_font
            candidate_font.setPointSizeF(candidate_size)
            candidate_layout, candidate_lines, candidate_total_height = self._build_layout_for_font(
                candidate_font,
                content_rect,
            )
            layout = candidate_layout
            lines = candidate_lines
            total_height = candidate_total_height
            chosen_size = candidate_size
            if total_height <= content_rect.height() or candidate_size <= minimum_size + 0.001:
                break
            candidate_size = round(candidate_size - 0.5, 2)

        if layout is None:
            return

        self._layout = layout
        self._layout_total_height = total_height
        self._fitted_point_size = chosen_size
        self._word_rects = self._build_word_rects(lines)

    def _build_layout_for_font(self, font, content_rect):
        layout = QTextLayout(self._raw_text, font)
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(text_option)
        layout.setFormats(self._build_format_ranges())

        lines = []
        total_height = 0.0
        layout.beginLayout()
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(content_rect.width())
            line.setPosition(QPointF(0.0, total_height))
            lines.append(line)
            total_height += line.height()
        layout.endLayout()

        if not lines:
            return layout, lines, total_height

        y_offset = content_rect.top() + max(0.0, (content_rect.height() - total_height) / 2.0)
        for line in lines:
            line_width = min(line.naturalTextWidth(), content_rect.width())
            x_offset = content_rect.left() + max(0.0, (content_rect.width() - line_width) / 2.0)
            line.setPosition(QPointF(x_offset, y_offset + line.position().y()))

        return layout, lines, total_height

    def _build_word_rects(self, lines):
        word_rects = [[] for _ in self._words]
        for word_index, word in enumerate(self._words):
            for line in lines:
                line_start = line.textStart()
                line_end = line_start + line.textLength()
                overlap_start = max(word.start, line_start)
                overlap_end = min(word.end, line_end)
                if overlap_start >= overlap_end:
                    continue

                start_x = self._cursor_x(line, overlap_start)
                end_x = self._cursor_x(line, overlap_end)
                left = min(start_x, end_x)
                width = max(1.0, abs(end_x - start_x))
                rect = QRectF(left, line.position().y(), width, line.height())
                word_rects[word_index].append(rect)
        return word_rects

    def _validate_coordinate_system(self):
        """Internal validation to ensure coordinate system consistency.

        This method checks that word rectangles are correctly positioned within
        the widget bounds and content rect. Only called in debug/test scenarios.

        Returns:
            bool: True if coordinate system is consistent, False otherwise
        """
        if not self._word_rects or not self._layout:
            return True

        content_rect = self._content_rect()
        widget_rect = QRectF(self.rect())

        for word_index, rects in enumerate(self._word_rects):
            for rect in rects:
                # Word rects should be within widget bounds (with small tolerance for rounding)
                if not widget_rect.adjusted(-1, -1, 1, 1).contains(rect):
                    print(f"Warning: Word {word_index} rect {rect} outside widget bounds {widget_rect}")
                    return False

                # Word rects should generally be within or near content rect
                # (may slightly exceed due to text overflow)
                if not content_rect.adjusted(-50, -5, 50, 5).contains(rect.center()):
                    print(f"Warning: Word {word_index} rect center far from content rect")
                    # Don't return False - this is just suspicious, not necessarily wrong

        return True

    def _build_format_ranges(self):
        ranges = []
        if self._raw_text:
            base_format = QTextCharFormat()
            base_format.setForeground(QColor("white"))
            base_range = QTextLayout.FormatRange()
            base_range.start = 0
            base_range.length = len(self._raw_text)
            base_range.format = base_format
            ranges.append(base_range)

        for index in sorted(self._highlighted_indices):
            if index < 0 or index >= len(self._words):
                continue
            word = self._words[index]
            if word.end <= word.start:
                continue
            text_format = QTextCharFormat()
            text_format.setBackground(QColor("yellow"))
            text_format.setForeground(QColor("black"))
            format_range = QTextLayout.FormatRange()
            format_range.start = word.start
            format_range.length = word.end - word.start
            format_range.format = text_format
            ranges.append(format_range)
        return ranges

    def _cursor_x(self, line, cursor_pos):
        value = line.cursorToX(cursor_pos)
        if isinstance(value, tuple):
            return float(value[0])
        return float(value)

    def _word_at_position(self, pos):
        """Find the word at the given position in widget coordinates.

        Args:
            pos: Position in widget coordinate space (QPointF or similar).
                 Widget coordinates have origin (0,0) at the top-left of the widget.

        Returns:
            Tuple of (word_text, word_index) if a word is found at the position,
            None otherwise.

        Coordinate System Notes:
            - Mouse events provide positions in widget space (origin at widget top-left)
            - Word rectangles in _word_rects are stored in widget space
            - Content rect margins are already included in word rectangle positions
            - Therefore, we compare mouse position directly with word rectangles
        """
        self._ensure_layout()
        if not self._word_rects:
            return None

        # Convert pos to QPointF if needed
        point = pos if isinstance(pos, QPointF) else QPointF(float(pos.x()), float(pos.y()))

        # Check each word rectangle directly - they're already in widget coordinate space
        for index, rects in enumerate(self._word_rects):
            for rect in rects:
                if rect.contains(point):
                    return self._words[index].word, index
        return None
