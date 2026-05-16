"""PDF document service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz
from PySide6.QtCore import QObject, Signal


@dataclass
class PdfRenderResult:
    page_index: int
    page_count: int
    width: int
    height: int
    stride: int
    samples: bytes
    words: list[tuple]
    word_order: list[tuple]
    line_map: dict[tuple[int, int], list[tuple]]


class PDFService(QObject):
    document_loaded = Signal(str, int)
    document_closed = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.doc = None
        self.current_path = ""

    def load_document(self, path: str):
        doc = fitz.open(path)
        self.close_document()
        self.doc = doc
        self.current_path = path
        self.document_loaded.emit(path, doc.page_count)
        return doc

    def close_document(self):
        if self.doc is not None:
            self.doc.close()
            self.doc = None
            self.current_path = ""
            self.document_closed.emit()

    def page_count(self) -> int:
        return 0 if self.doc is None else self.doc.page_count

    def render_page(self, page_index: int, zoom_factor: float) -> PdfRenderResult | None:
        if self.doc is None:
            return None
        page = self.doc.load_page(page_index)
        matrix = fitz.Matrix(zoom_factor, zoom_factor)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        words = page.get_text("words")
        word_order = sorted(words, key=lambda w: (int(w[5]), int(w[6]), int(w[7]), float(w[1]), float(w[0])))
        return PdfRenderResult(
            page_index=page_index,
            page_count=self.doc.page_count,
            width=pix.width,
            height=pix.height,
            stride=pix.stride,
            samples=bytes(pix.samples),
            words=words,
            word_order=word_order,
            line_map=self.build_line_index(words),
        )

    def build_line_index(self, words: list[tuple]) -> dict[tuple[int, int], list[tuple]]:
        line_map: dict[tuple[int, int], list[tuple]] = {}
        for word in words:
            key = (int(word[5]), int(word[6]))
            line_map.setdefault(key, []).append(word)
        for key in line_map:
            line_map[key].sort(key=lambda item: item[0])
        return line_map

    def word_key(self, word: tuple):
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

    def word_at_point(self, word_order: list[tuple], x_pdf: float, y_pdf: float):
        for word in word_order:
            if word[0] <= x_pdf <= word[2] and word[1] <= y_pdf <= word[3]:
                return word
        return None

    def resolve_selected_words(self, hit_word: tuple, shift_pressed: bool, anchor_key: tuple | None, page_word_order: list[tuple], page_word_index: dict[tuple, int]):
        hit_key = self.word_key(hit_word)
        if not shift_pressed or anchor_key is None:
            return [hit_word], hit_key
        anchor_index = page_word_index.get(anchor_key)
        hit_index = page_word_index.get(hit_key)
        if anchor_index is None or hit_index is None:
            return [hit_word], hit_key
        start_idx = min(anchor_index, hit_index)
        end_idx = max(anchor_index, hit_index)
        return page_word_order[start_idx : end_idx + 1], anchor_key

    def extract_context(self, selected_words: list[tuple], line_map: dict[tuple[int, int], list[tuple]]) -> str:
        if not selected_words:
            return ""
        line_key = (int(selected_words[0][5]), int(selected_words[0][6]))
        line_words = line_map.get(line_key, [selected_words[0]])
        return " ".join(item[4] for item in line_words)

    def source_name(self) -> str:
        return Path(self.current_path).name if self.current_path else ""

    def merge_highlight_bboxes(self, selected_words: list[tuple]) -> list[tuple[float, float, float, float]]:
        """
        Merge bounding boxes for consecutive words on the same line into continuous highlights.

        Args:
            selected_words: List of word tuples with structure (x0, y0, x1, y1, text, block, line, word_num, ...)

        Returns:
            List of merged bounding boxes (x0, y0, x1, y1) - one per line
        """
        if not selected_words:
            return []

        # Group words by line (block number and line number)
        lines = {}
        for word in selected_words:
            line_key = (int(word[5]), int(word[6]))
            if line_key not in lines:
                lines[line_key] = []
            lines[line_key].append(word)

        # Create merged bounding boxes for each line
        merged_bboxes = []
        for line_words in lines.values():
            # Find the extents of all words on this line
            x0 = min(w[0] for w in line_words)
            y0 = min(w[1] for w in line_words)
            x1 = max(w[2] for w in line_words)
            y1 = max(w[3] for w in line_words)
            merged_bboxes.append((x0, y0, x1, y1))

        return merged_bboxes
