"""Selection state management for PDF and video modes."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class PdfSelectionState:
    """PDF-specific selection state."""
    selected_words: List[Tuple] = field(default_factory=list)
    highlight_bboxes: List[Tuple[float, float, float, float]] = field(default_factory=list)
    anchor_key: Optional[Tuple] = None

    def clear(self):
        self.selected_words.clear()
        self.highlight_bboxes.clear()
        self.anchor_key = None

    def is_empty(self) -> bool:
        return not self.selected_words


@dataclass
class VideoSelectionState:
    """Video-specific selection state."""
    selected_indices: List[int] = field(default_factory=list)
    anchor: Optional[Tuple[int, int]] = None

    def clear(self):
        self.selected_indices.clear()
        self.anchor = None

    def is_empty(self) -> bool:
        return not self.selected_indices


@dataclass
class SelectionState:
    """
    Unified selection state container.
    Owns both PDF and video selection, only one active at a time.
    """
    word: str = ""
    sentence: str = ""
    translation: str = ""

    pdf: PdfSelectionState = field(default_factory=PdfSelectionState)
    video: VideoSelectionState = field(default_factory=VideoSelectionState)

    def clear_all(self):
        self.word = ""
        self.sentence = ""
        self.translation = ""
        self.pdf.clear()
        self.video.clear()
