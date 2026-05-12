"""Video subtitle state service."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from immersion_app.media.subtitle_parser import SRTParser


class VideoService(QObject):
    subtitles_loaded = Signal(int)
    subtitles_cleared = Signal()

    def __init__(self, subtitle_offset_ms: int = 0, parent: QObject | None = None):
        super().__init__(parent)
        self.subtitle_parser: SRTParser | None = None
        self.current_srt_path = ""
        self.subtitle_offset_ms = subtitle_offset_ms

    def load_subtitles(self, srt_path: str):
        self.subtitle_parser = SRTParser.from_file(srt_path)
        self.current_srt_path = srt_path
        self.subtitles_loaded.emit(len(self.subtitle_parser.subtitles))
        return self.subtitle_parser

    def clear_subtitles(self):
        self.subtitle_parser = None
        self.current_srt_path = ""
        self.subtitles_cleared.emit()

    def subtitle_at_position(self, position_ms: int):
        if self.subtitle_parser is None:
            return None
        lookup_position = max(0, position_ms - self.subtitle_offset_ms)
        return self.subtitle_parser.get_subtitle_at_time(lookup_position)

    def set_offset(self, milliseconds: int):
        self.subtitle_offset_ms = milliseconds

    def resolve_selection_range(
        self,
        token_index: int,
        shift_pressed: bool,
        current_anchor: tuple[int, int] | None,
        subtitle_index: int,
        token_count: int,
    ):
        if not shift_pressed or current_anchor is None or current_anchor[0] != subtitle_index:
            return [token_index], (subtitle_index, token_index)
        anchor_index = max(0, min(current_anchor[1], token_count - 1))
        start = min(anchor_index, token_index)
        end = max(anchor_index, token_index)
        return list(range(start, end + 1)), current_anchor

    def source_subtitle_name(self) -> str:
        return Path(self.current_srt_path).name if self.current_srt_path else ""
