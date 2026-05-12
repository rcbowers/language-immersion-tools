"""Selection state management for PDF and video modes."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal


@dataclass
class PdfSelectionState:
    """PDF-specific selection state."""

    selected_words: list[tuple] = field(default_factory=list)
    highlight_bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    anchor_key: tuple | None = None

    def clear(self):
        self.selected_words.clear()
        self.highlight_bboxes.clear()
        self.anchor_key = None

    def is_empty(self) -> bool:
        return not self.selected_words


@dataclass
class VideoSelectionState:
    """Video-specific selection state."""

    selected_indices: list[int] = field(default_factory=list)
    anchor: tuple[int, int] | None = None

    def clear(self):
        self.selected_indices.clear()
        self.anchor = None

    def is_empty(self) -> bool:
        return not self.selected_indices


class SelectionState(QObject):
    """
    Unified selection state container.

    This is the single source of truth for the current mined selection.
    """

    selection_changed = Signal()
    translation_changed = Signal(str)
    cleared = Signal()

    def __init__(
        self,
        word: str = "",
        sentence: str = "",
        translation: str = "",
        pdf: PdfSelectionState | None = None,
        video: VideoSelectionState | None = None,
    ):
        super().__init__()
        self.word = word
        self.sentence = sentence
        self.translation = translation
        self.pdf = pdf or PdfSelectionState()
        self.video = video or VideoSelectionState()

    def set_manual_word(self, word: str):
        self.word = word
        self.sentence = ""
        self.translation = ""
        self.pdf.clear()
        self.video.clear()
        self.selection_changed.emit()
        self.translation_changed.emit(self.translation)

    def set_pdf_selection(self, *, word: str, sentence: str, selected_words: list[tuple], highlight_bboxes: list[tuple]):
        self.word = word
        self.sentence = sentence
        self.translation = ""
        self.pdf.selected_words = list(selected_words)
        self.pdf.highlight_bboxes = list(highlight_bboxes)
        self.video.clear()
        self.selection_changed.emit()
        self.translation_changed.emit(self.translation)

    def set_video_selection(self, *, word: str, sentence: str, selected_indices: list[int], anchor: tuple[int, int] | None):
        self.word = word
        self.sentence = sentence
        self.translation = ""
        self.video.selected_indices = list(selected_indices)
        self.video.anchor = anchor
        self.pdf.clear()
        self.selection_changed.emit()
        self.translation_changed.emit(self.translation)

    def set_translation_pending(self):
        self.translation = "translating..."
        self.translation_changed.emit(self.translation)
        self.selection_changed.emit()

    def set_translation(self, translation: str):
        self.translation = translation
        self.translation_changed.emit(translation)
        self.selection_changed.emit()

    def set_translation_error(self, error_message: str):
        self.set_translation(f"Translation error: {error_message}")

    def clear_all(self):
        self.word = ""
        self.sentence = ""
        self.translation = ""
        self.pdf.clear()
        self.video.clear()
        self.cleared.emit()
        self.translation_changed.emit(self.translation)
        self.selection_changed.emit()
