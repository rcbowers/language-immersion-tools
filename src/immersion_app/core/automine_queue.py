"""Parse the automatic miner's queue file into per-source sections.

A line starting with ``#`` names a source (a local file path or a web URL);
the non-blank lines beneath it are the words to mine from that source.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QueueSection:
    """A source and the words queued for mining from it."""

    source: str
    queries: list[str] = field(default_factory=list)


def is_url(source: str) -> bool:
    """Return True when *source* names a web page rather than a local file."""
    return source.lower().startswith(("http://", "https://"))


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
