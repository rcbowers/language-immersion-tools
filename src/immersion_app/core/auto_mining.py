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
    match_start: int | None = None
    match_end: int | None = None
    preceding_words: tuple[str, ...] = ()
    following_words: tuple[str, ...] = ()


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

    contexts = list(contexts)
    candidates: list[MiningCandidate] = []
    for context_index, context in enumerate(contexts):
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
                    match_start=start,
                    match_end=end,
                    preceding_words=_nearby_words(contexts, context_index, -1),
                    following_words=_nearby_words(contexts, context_index, 1),
                )
            )
    return candidates


def context_window_bounds(candidate: MiningCandidate) -> tuple[int, int]:
    """Return the initial, whole-sentence word bounds for *candidate*."""
    start = len(candidate.preceding_words)
    return (start, start + len(_sentence_words(candidate)))


def adjust_context_window(
    candidate: MiningCandidate,
    bounds: tuple[int, int],
    direction: str,
) -> tuple[int, int]:
    """Move one context-window bound without excluding the matched text.

    ``start_backward`` and ``start_forward`` adjust the beginning; ``end_backward``
    and ``end_forward`` adjust the end.  Bounds are word indexes with an exclusive
    end, which keeps punctuation attached to its word in the rendered context.
    """
    words = _context_words(candidate)
    if not words:
        return (0, 0)

    start, end = bounds
    start = max(0, min(start, len(words)))
    end = max(start, min(end, len(words)))
    protected_start, protected_end = _matched_word_bounds(candidate)

    if direction == "start_backward":
        start = max(0, start - 1)
    elif direction == "start_forward":
        start = min(protected_start, start + 1)
    elif direction == "end_backward":
        end = max(protected_end, end - 1)
    elif direction == "end_forward":
        end = min(len(words), end + 1)
    else:
        raise ValueError(f"Unknown context-window direction: {direction}")
    return (start, end)


def render_context_window(candidate: MiningCandidate, bounds: tuple[int, int]) -> str:
    """Render the selected word-range of a candidate's source sentence."""
    words = _context_words(candidate)
    start, end = bounds
    if not words or start >= end:
        return ""
    return " ".join(words[start:end])


def render_context_neighbor_words(
    candidate: MiningCandidate, bounds: tuple[int, int], *, limit: int = 5
) -> tuple[str, str]:
    """Return up to *limit* source words on each side of a context window."""
    words = _context_words(candidate)
    start, end = bounds
    if not words or start >= end:
        return ("", "")
    before_start = max(0, start - limit)
    after_end = min(len(words), end + limit)
    return (
        " ".join(words[before_start:start]),
        " ".join(words[end:after_end]),
    )


def _word_spans(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in re.finditer(r"\S+", text)]


def _match_character_bounds(candidate: MiningCandidate) -> tuple[int, int]:
    """Return the source offsets of this exact occurrence, with legacy fallback."""
    if candidate.match_start is not None and candidate.match_end is not None:
        return (candidate.match_start, candidate.match_end)
    start = candidate.sentence.find(candidate.matched_text)
    if start < 0:
        return (0, 0)
    return (start, start + len(candidate.matched_text))


def _sentence_words(candidate: MiningCandidate) -> list[str]:
    return [candidate.sentence[start:end] for start, end in _word_spans(candidate.sentence)]


def _context_words(candidate: MiningCandidate) -> list[str]:
    return [*candidate.preceding_words, *_sentence_words(candidate), *candidate.following_words]


def _matched_word_bounds(candidate: MiningCandidate) -> tuple[int, int]:
    """Return the selected phrase's word bounds within the extendable context."""
    spans = _word_spans(candidate.sentence)
    match_start, match_end = _match_character_bounds(candidate)
    sentence_start = next(
        (index for index, (_, word_end) in enumerate(spans) if word_end > match_start),
        0,
    )
    sentence_end = max(
        (index + 1 for index, (word_start, _) in enumerate(spans) if word_start < match_end),
        default=0,
    )
    offset = len(candidate.preceding_words)
    return (offset + sentence_start, offset + sentence_end)


def _nearby_words(
    contexts: list[MiningContext], context_index: int, direction: int, *, limit: int = 5
) -> tuple[str, ...]:
    """Return the nearest same-source words outside a candidate's sentence."""
    current = contexts[context_index]
    words: list[str] = []
    index = context_index + direction
    while 0 <= index < len(contexts) and len(words) < limit:
        neighbor = contexts[index]
        if neighbor.source_name != current.source_name:
            break
        neighbor_words = _sentence_words_from_text(neighbor.text)
        if direction < 0:
            words.extend(reversed(neighbor_words))
        else:
            words.extend(neighbor_words)
        index += direction
    words = words[:limit]
    if direction < 0:
        words.reverse()
    return tuple(words)


def _sentence_words_from_text(text: str) -> list[str]:
    return [text[start:end] for start, end in _word_spans(text)]
