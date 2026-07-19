"""Domain matching logic for the interactive automatic miner."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable, Protocol


_APOSTROPHES = frozenset("'\u2018\u2019\u201b\u2032\uff07")


class MiningContext(Protocol):
    """The source data needed by the core matcher, supplied by a media adapter."""

    text: str
    source_name: str
    location: str


@dataclass(frozen=True)
class MiningCandidate:
    """A source occurrence that can be reviewed and made into a card."""

    query: str
    matched_text: str
    sentence: str
    source_name: str
    location: str


def _fold_with_offsets(text: str) -> tuple[str, list[int]]:
    """Case- and accent-fold text while mapping each output character to its source."""
    output: list[str] = []
    offsets: list[int] = []
    for index, character in enumerate(text):
        if character in _APOSTROPHES:
            folded = "'"
        elif character.isspace():
            folded = " "
        else:
            decomposed = unicodedata.normalize("NFKD", character.casefold())
            folded = "".join(part for part in decomposed if not unicodedata.combining(part))
        for part in folded:
            output.append(part)
            offsets.append(index)
    return "".join(output), offsets


def normalize_for_match(text: str) -> str:
    """Public normalized form used for accent- and apostrophe-flexible matching."""
    return _fold_with_offsets(text)[0]


def _query_pattern(query: str) -> re.Pattern[str] | None:
    normalized = normalize_for_match(query).strip()
    if not normalized:
        return None
    escaped = re.escape(normalized)
    escaped = re.sub(r"(?:\\ )+", r"\\s+", escaped)
    return re.compile(rf"(?<!\w)({escaped})(?!\w)")


def find_candidates(query: str, contexts: Iterable[MiningContext]) -> list[MiningCandidate]:
    """Find normalized exact occurrences of a query in the supplied contexts."""
    pattern = _query_pattern(query)
    if pattern is None:
        return []

    candidates: list[MiningCandidate] = []
    for context in contexts:
        normalized, offsets = _fold_with_offsets(context.text)
        for match in pattern.finditer(normalized):
            start = offsets[match.start(1)]
            end = offsets[match.end(1) - 1] + 1
            candidates.append(
                MiningCandidate(
                    query=query,
                    matched_text=context.text[start:end],
                    sentence=context.text,
                    source_name=context.source_name,
                    location=context.location,
                )
            )
    return candidates
