"""Parse the automatic miner's queue file into per-source sections.

A line starting with ``#`` names a source (a local file path or a web URL);
the non-blank lines beneath it are the words to mine from that source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass
class QueueSection:
    """A source and the words queued for mining from it."""

    source: str
    queries: list[str] = field(default_factory=list)


def is_url(source: str) -> bool:
    """Return True when *source* names a web page rather than a local file."""
    return source.lower().startswith(("http://", "https://"))


INLINE_SOURCE = "none"
_BRACKETED = re.compile(r"\[([^\[\]]+)\]")


def is_inline_source(source: str) -> bool:
    """Return True for the ``# none ...`` section, whose lines are their own contexts."""
    return source.strip().lower().startswith(INLINE_SOURCE)


def parse_inline_context(line: str) -> tuple[str, str, int, int] | None:
    """Split ``sentence with [word]`` into (word, sentence, start, end).

    The sentence has its brackets removed; start/end locate the word within it.
    Returns None when the line has no bracketed word.
    """
    line = line.strip()
    match = _BRACKETED.search(line)
    if match is None:
        return None
    word = match.group(1)
    sentence = line[: match.start()] + word + line[match.end() :]
    return word.strip(), sentence, match.start(), match.start() + len(word)


def _header_source(line: str) -> str:
    """Return the source named by a ``#`` header line, without surrounding quotes."""
    title = line.lstrip("#").strip()
    if len(title) >= 2 and title[0] == title[-1] and title[0] in "\"'":
        title = title[1:-1].strip()
    return title


def parse_queue_sections(text: str) -> list[QueueSection]:
    """Split queue text into sections; words before any header and empty sections are dropped."""
    sections: list[QueueSection] = []
    current: QueueSection | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            current = QueueSection(_header_source(line))
            sections.append(current)
        elif current is not None:
            current.queries.append(line)
    return [section for section in sections if section.source and section.queries]


def remove_query_from_section(text: str, source: str, query: str) -> str:
    """Remove the first *query* line under *source*'s header, leaving other sections intact."""
    lines = text.splitlines(keepends=True)
    in_section = False
    for index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.startswith("#"):
            in_section = _header_source(line) == source
        elif in_section and line == query:
            del lines[index]
            return "".join(lines)
    raise ValueError(f"Approved query is no longer present under '{source}': {query}")
