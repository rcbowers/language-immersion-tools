"""PDF document service."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pymupdf
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from immersion_app.core.perf import perf_timed
from immersion_app.core.signals import safe_emit


# Reflowable documents (EPUB) are laid out onto fixed-size pages so every downstream consumer
# (render cache, completion tracking, page navigation) sees ordinary, stable pages.
EPUB_PAGE_WIDTH = 600.0
EPUB_PAGE_HEIGHT = 800.0
EPUB_FONT_SIZE = 11.0
DOC_KIND_PDF = "pdf"
DOC_KIND_EPUB = "epub"
REFLOWABLE_SUFFIXES = {".epub"}
MAX_SENTENCE_CONTEXT_CHARS = 400


def doc_kind_for_path(path: str) -> str:
    """Document kind ("pdf" or "epub") derived from the file suffix."""
    return DOC_KIND_EPUB if Path(path).suffix.lower() in REFLOWABLE_SUFFIXES else DOC_KIND_PDF


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
    zoom_factor: float = 1.0
    dark: bool = False

    @property
    def nbytes(self) -> int:
        return len(self.samples)


class _RenderTaskSignals(QObject):
    # request_id, generation, tag, result (None when the task was skipped as stale)
    finished = Signal(int, int, object, object)
    failed = Signal(int, int, object, str)


class PdfRenderTask(QRunnable):
    """Rasterize one page on a worker thread.

    Emits ``finished`` with ``result=None`` when ``is_stale()`` is true at start,
    so callers can clear their in-flight bookkeeping without doing the work.
    """

    def __init__(self, service: "PDFService", page_index: int, zoom_factor: float, dark: bool,
                 request_id: int, generation: int, tag, is_stale: Callable[[], bool]):
        super().__init__()
        self.service = service
        self.page_index = page_index
        self.zoom_factor = zoom_factor
        self.dark = dark
        self.request_id = request_id
        self.generation = generation
        self.tag = tag
        self.is_stale = is_stale
        self.signals = _RenderTaskSignals()

    def run(self):
        try:
            if self.is_stale():
                safe_emit(self.signals.finished, self.request_id, self.generation, self.tag, None)
                return
            result = self.service.render_page(self.page_index, self.zoom_factor, self.dark)
        except Exception as exc:
            safe_emit(self.signals.failed, self.request_id, self.generation, self.tag, str(exc))
            return
        safe_emit(self.signals.finished, self.request_id, self.generation, self.tag, result)


class PDFService(QObject):
    document_loaded = Signal(str, int)
    document_closed = Signal()
    # request_id, generation, tag, result (None = skipped as stale)
    page_rendered = Signal(int, int, object, object)
    page_render_failed = Signal(int, int, object, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.doc = None
        self.current_path = ""
        # ``pymupdf.Document`` is not safe for concurrent use: every access goes through this lock.
        self._doc_lock = threading.RLock()
        self._page_sizes: dict[int, tuple[float, float]] = {}
        # One dedicated render thread so page rendering never starves the global pool
        # (translation, Anki, previews) and renders run strictly in priority order.
        self._render_pool = QThreadPool(self)
        self._render_pool.setMaxThreadCount(1)

    def load_document(self, path: str):
        doc = pymupdf.open(path)
        if doc.is_reflowable:
            doc.layout(width=EPUB_PAGE_WIDTH, height=EPUB_PAGE_HEIGHT, fontsize=EPUB_FONT_SIZE)
        self.close_document()
        with self._doc_lock:
            self.doc = doc
            self.current_path = path
            self._page_sizes = {}
        self.document_loaded.emit(path, doc.page_count)
        return doc

    @property
    def doc_kind(self) -> str:
        """"epub" for reflowable documents, otherwise "pdf"."""
        return doc_kind_for_path(self.current_path) if self.current_path else DOC_KIND_PDF

    @property
    def is_reflowable(self) -> bool:
        return self.doc is not None and bool(self.doc.is_reflowable)

    def get_toc(self) -> list[tuple[int, str, int]]:
        """Table of contents as ``(level, title, 0-based page index)`` entries."""
        with self._doc_lock:
            if self.doc is None:
                return []
            entries = []
            for level, title, page in self.doc.get_toc():
                if page >= 1:
                    entries.append((int(level), str(title), int(page) - 1))
            return entries

    def location_for_page(self, page_index: int) -> tuple[int, int] | None:
        """Layout-independent-ish ``(chapter, page_in_chapter)`` for reflowable docs, else None."""
        with self._doc_lock:
            if not self.is_reflowable or not (0 <= page_index < self.doc.page_count):
                return None
            chapter, page = self.doc.location_from_page_number(page_index)
            return int(chapter), int(page)

    def page_for_location(self, chapter: int, page: int) -> int | None:
        """Inverse of ``location_for_page``; None when unavailable or out of range."""
        with self._doc_lock:
            if not self.is_reflowable:
                return None
            try:
                index = int(self.doc.page_number_from_location((int(chapter), int(page))))
            except Exception:
                return None
            return index if 0 <= index < self.doc.page_count else None

    def close_document(self):
        with self._doc_lock:
            had_doc = self.doc is not None
            if had_doc:
                self.doc.close()
                self.doc = None
                self.current_path = ""
                self._page_sizes = {}
        if had_doc:
            self.document_closed.emit()

    def page_size(self, page_index: int) -> tuple[float, float]:
        """Page size in PDF points. Cached so the UI thread rarely waits on the render lock."""
        cached = self._page_sizes.get(page_index)
        if cached is not None:
            return cached
        with self._doc_lock:
            rect = self.doc.load_page(page_index).rect
            size = (float(rect.width), float(rect.height))
            self._page_sizes[page_index] = size
        return size

    def render_async(self, page_index: int, zoom_factor: float, dark: bool, request_id: int, generation: int,
                     tag, is_stale: Callable[[], bool], priority: int = 0) -> PdfRenderTask:
        """Queue a render; results arrive on the UI thread via ``page_rendered`` / ``page_render_failed``."""
        task = PdfRenderTask(self, page_index, zoom_factor, dark, request_id, generation, tag, is_stale)
        # Connecting to QObject methods makes Qt queue the delivery onto the UI thread.
        task.signals.finished.connect(self._on_render_finished)
        task.signals.failed.connect(self._on_render_failed)
        self._render_pool.start(task, priority)
        return task

    def _on_render_finished(self, request_id, generation, tag, result):
        self.page_rendered.emit(request_id, generation, tag, result)

    def _on_render_failed(self, request_id, generation, tag, message):
        self.page_render_failed.emit(request_id, generation, tag, message)

    def wait_for_renders(self, timeout_ms: int = 5000) -> bool:
        return self._render_pool.waitForDone(timeout_ms)

    def page_count(self) -> int:
        return 0 if self.doc is None else self.doc.page_count

    @perf_timed("pdf_service.render_page")
    def render_page(self, page_index: int, zoom_factor: float, dark: bool = False) -> PdfRenderResult | None:
        """Rasterize a page plus its word boxes. Pure page content: no selection/vocabulary highlights.

        Safe to call from a worker thread. ``dark`` inverts the page colours.
        """
        with self._doc_lock:
            if self.doc is None:
                return None
            page = self.doc.load_page(page_index)
            matrix = pymupdf.Matrix(zoom_factor, zoom_factor)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            if dark:
                pix.invert_irect()
            words = page.get_text("words")
            page_count = self.doc.page_count
            rect = page.rect
            self._page_sizes[page_index] = (float(rect.width), float(rect.height))
            width, height, stride, samples = pix.width, pix.height, pix.stride, bytes(pix.samples)
        word_order = sorted(words, key=lambda w: (int(w[5]), int(w[6]), int(w[7]), float(w[1]), float(w[0])))
        return PdfRenderResult(
            page_index=page_index,
            page_count=page_count,
            width=width,
            height=height,
            stride=stride,
            samples=samples,
            words=words,
            word_order=word_order,
            line_map=self.build_line_index(words),
            zoom_factor=zoom_factor,
            dark=dark,
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
        line_text = " ".join(item[4] for item in line_words)
        if not self.is_reflowable:
            return line_text
        # Book text flows across lines, so a full sentence is a better mining context than one line.
        return self._sentence_context(selected_words[0], line_map) or line_text

    def _sentence_context(self, word: tuple, line_map: dict[tuple[int, int], list[tuple]]) -> str:
        """The punctuation-delimited sentence on the page containing ``word`` ("" if it can't be found)."""
        # Sentences never cross a block (paragraph/heading) boundary, so only the word's own block is searched.
        block = int(word[5])
        pieces: list[str] = []
        start = None
        offset = 0
        for key in sorted(k for k in line_map if k[0] == block):
            for item in line_map[key]:
                if key[1] == int(word[6]) and int(item[7]) == int(word[7]):
                    start = offset
                pieces.append(str(item[4]))
                offset += len(item[4]) + 1
        if start is None:
            return ""
        text = " ".join(pieces)
        for match in re.finditer(r"[^.!?…]+(?:[.!?…]+|$)", text, flags=re.DOTALL):
            if match.start() <= start < match.end():
                sentence = " ".join(match.group(0).split())
                return sentence if len(sentence) <= MAX_SENTENCE_CONTEXT_CHARS else ""
        return ""

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
