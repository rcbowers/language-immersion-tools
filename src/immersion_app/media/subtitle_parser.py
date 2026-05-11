#!/usr/bin/env python3
"""SRT subtitle parsing and lookup utilities."""

from dataclasses import dataclass
import bisect
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class SubtitleWord:
    word: str
    start: int
    end: int


@dataclass
class SRTSubtitle:
    index: int
    start_ms: int
    end_ms: int
    text: str
    words: list[SubtitleWord]


class SRTParser:
    TIMESTAMP_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")

    def __init__(self, subtitles=None):
        self.subtitles = subtitles or []
        self._starts = [s.start_ms for s in self.subtitles]

    @classmethod
    def parse_timestamp(cls, value):
        match = cls.TIMESTAMP_RE.fullmatch(value.strip())
        if not match:
            raise ValueError(f"Invalid SRT timestamp: {value}")
        hh, mm, ss, ms = map(int, match.groups())
        return ((hh * 60 + mm) * 60 + ss) * 1000 + ms

    @classmethod
    def _extract_words(cls, text):
        words = []
        for match in re.finditer(r"\b[^\W_]+\b", text, flags=re.UNICODE):
            words.append(SubtitleWord(word=match.group(0), start=match.start(), end=match.end()))
        return words

    @classmethod
    def from_file(cls, path):
        logger.info(f"Loading subtitle file: {path}")
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                content = handle.read()
            parser = cls.from_text(content)
            logger.info(f"Subtitle file loaded: {len(parser.subtitles)} entries parsed from {path}")
            return parser
        except Exception as e:
            logger.error(f"Failed to load subtitle file {path}: {e}", exc_info=True)
            raise

    @classmethod
    def from_text(cls, content):
        blocks = re.split(r"\r?\n\r?\n+", content.strip())
        subtitles = []
        inferred_index = 1

        for block in blocks:
            lines = [line.rstrip("\r") for line in block.splitlines() if line.strip()]
            if len(lines) < 2:
                continue

            line_offset = 0
            if re.fullmatch(r"\d+", lines[0]):
                index = int(lines[0])
                line_offset = 1
            else:
                index = inferred_index

            if line_offset >= len(lines):
                continue

            timing = lines[line_offset]
            if "-->" not in timing:
                continue
            start_text, end_text = [part.strip() for part in timing.split("-->", 1)]

            try:
                start_ms = cls.parse_timestamp(start_text)
                end_ms = cls.parse_timestamp(end_text.split()[0])
            except ValueError:
                continue

            text = " ".join(lines[line_offset + 1 :]).strip()
            if not text:
                continue

            subtitles.append(
                SRTSubtitle(
                    index=index,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                    words=cls._extract_words(text),
                )
            )
            inferred_index += 1

        subtitles.sort(key=lambda s: s.start_ms)
        return cls(subtitles)

    def get_subtitle_at_time(self, time_ms):
        if not self.subtitles:
            return None

        i = bisect.bisect_right(self._starts, time_ms) - 1
        if i < 0:
            return None

        candidate = self.subtitles[i]
        if candidate.start_ms <= time_ms <= candidate.end_ms:
            return candidate
        return None
