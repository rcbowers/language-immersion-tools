#!/usr/bin/env python3
"""Interactively mine phrases into LinguaLoop Anki cards.

The queue file groups words under ``# <source>`` headers, where the source is a
local PDF/SRT path or a web URL.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Callable, Iterable, Sequence
import unicodedata


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from immersion_app.core.anki import add_anki_card, start_anki_if_needed, test_anki_connection
from immersion_app.core.automine_queue import (
    QueueSection,
    is_inline_source,
    parse_inline_context,
    parse_queue_sections,
    remove_query_from_section,
)
from immersion_app.core.auto_mining import (
    MiningCandidate,
    MiningContext,
    adjust_context_window,
    context_window_bounds,
    find_candidates,
    render_context_neighbor_words,
    render_context_window,
)
from immersion_app.core.language_config import (
    SUPPORTED_LANGUAGES,
    get_google_language_code,
    get_marian_language_code,
)
from immersion_app.integrations.translation_backends import (
    MarianMTTranslationBackend,
    OnlineTranslationBackend,
    TranslationBackend,
)
from immersion_app.media.source_context import load_source_contexts


# Keep the bundled queue available regardless of the directory from which the
# command is launched. Explicit input-file arguments remain relative to the
# caller's current directory.
DEFAULT_INPUT_FILE = PROJECT_ROOT / "automine_inputs.txt"
CARD_MIN_CONTENT_WIDTH = 40
CARD_MAX_CONTENT_WIDTH = 72
CARD_VERTICAL_PADDING = 2
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
RECENT_SOURCES_PATH = PROJECT_ROOT / "data" / "state" / "automine_recent_sources.json"
MAX_RECENT_SOURCES = 10


class FallbackTranslator:
    """Use local MarianMT after an online translation failure in this session."""

    def __init__(
        self,
        online_backend: TranslationBackend,
        offline_backend: TranslationBackend,
        *,
        online_source_code: str,
        online_target_code: str,
        offline_source_code: str,
        offline_target_code: str,
        notify: Callable[[str], None] = print,
    ):
        self._online_backend = online_backend
        self._offline_backend = offline_backend
        self._online_source_code = online_source_code
        self._online_target_code = online_target_code
        self._offline_source_code = offline_source_code
        self._offline_target_code = offline_target_code
        self._notify = notify
        self._using_offline = False

    def translate(self, text: str) -> str:
        """Translate *text*, permanently switching to local fallback on failure."""
        if self._using_offline:
            return self._translate_offline(text)
        try:
            return self._online_backend.translate(
                text, self._online_source_code, self._online_target_code
            )
        except Exception as online_error:
            self._using_offline = True
            self._notify(
                "Google Translate is unavailable; switching to local MarianMT "
                "for the rest of this session. The first fallback translation "
                "may download a language model."
            )
            try:
                return self._translate_offline(text)
            except Exception as offline_error:
                raise RuntimeError(
                    "Online translation failed "
                    f"({online_error}); local MarianMT fallback also failed "
                    f"({offline_error})."
                ) from offline_error

    def _translate_offline(self, text: str) -> str:
        return self._offline_backend.translate(
            text, self._offline_source_code, self._offline_target_code
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input_file",
        nargs="?",
        type=Path,
        default=None,
        metavar="INPUT_FILE",
        help="Queue file with '# <source path or URL>' sections of words to mine.",
    )
    parser.add_argument("--source-lang", default="es", choices=sorted(SUPPORTED_LANGUAGES))
    parser.add_argument("--target-lang", default="en", choices=sorted(SUPPORTED_LANGUAGES))
    args = parser.parse_args(argv)
    if args.input_file is None:
        args.input_file = Path(DEFAULT_INPUT_FILE)
    return args


# The recent-sources picker below is disabled: sources now come from the '# '
# section headers in the queue file. Kept for possible reuse.
def load_recent_sources() -> list[str]:
    """Return recently used source document paths, newest first."""
    if not RECENT_SOURCES_PATH.is_file():
        return []
    try:
        data = json.loads(RECENT_SOURCES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def remember_recent_source(source_document: Path) -> None:
    """Move *source_document* to the front of the recent-sources list."""
    resolved = str(source_document.resolve())
    recent = [path for path in load_recent_sources() if path != resolved]
    recent.insert(0, resolved)
    recent = recent[:MAX_RECENT_SOURCES]
    RECENT_SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECENT_SOURCES_PATH.write_text(json.dumps(recent, indent=2), encoding="utf-8")


def prompt_for_source_document(
    recent_sources: Sequence[str], *, input_fn: Callable[[str], str] = input
) -> Path:
    """Ask the user to pick a source document from the recent-sources list."""
    if not recent_sources:
        raise FileNotFoundError(
            "No source document given and no recent sources saved yet. "
            "Pass a SOURCE_DOCUMENT the first time."
        )
    print("No source document given. Choose from recently used sources:")
    for index, path in enumerate(recent_sources, start=1):
        print(f"  {index}. {path}")
    while True:
        choice = input_fn(f"Enter number (1-{len(recent_sources)}): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(recent_sources):
            return Path(recent_sources[int(choice) - 1])
        print("Invalid selection.")


def load_queries(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def load_queue_sections(path: Path) -> list[QueueSection]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    return parse_queue_sections(path.read_text(encoding="utf-8-sig"))


def remove_section_query_from_queue(path: Path, source: str, query: str) -> None:
    """Remove an approved query from *source*'s section of the queue file."""
    text = path.read_text(encoding="utf-8-sig")
    path.write_text(remove_query_from_section(text, source, query), encoding="utf-8")


def inline_candidates(line: str) -> list[MiningCandidate]:
    """Build the single candidate for a '# none' line: a sentence with [word] in brackets."""
    parsed = parse_inline_context(line)
    if parsed is None:
        return []
    word, sentence, start, end = parsed
    return [
        MiningCandidate(
            query=line,
            matched_text=sentence[start:end],
            sentence=sentence,
            source_name="Pasted sentence",
            location="",
            match_start=start,
            match_end=end,
        )
    ]


def find_all_candidates(
    queries: Iterable[str], contexts: Iterable[MiningContext]
) -> list[list[MiningCandidate]]:
    """Find every query's occurrences before interactive review begins."""
    contexts = list(contexts)
    return [find_candidates(query, contexts) for query in queries]


def remove_query_from_queue(path: Path, query: str) -> None:
    """Remove the first queued query matching *query* after its card is created."""
    lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip() == query:
            del lines[index]
            path.write_text("".join(lines), encoding="utf-8")
            return
    raise ValueError(f"Approved query is no longer present in the input file: {query}")


def _read_key() -> str:
    """Read one navigation key from a Windows console."""
    if os.name != "nt":
        raise RuntimeError("auto_miner requires a Windows interactive terminal for arrow-key review.")
    try:
        import msvcrt

        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            key = msvcrt.getwch()
            return {"K": "left", "M": "right"}.get(key, "other")
        if key == "\r":
            return "enter"
        if key == "\x1b":
            return "escape"
        if key.lower() == "e":
            return "e"
        if key == ",":
            return "start_backward"
        if key == ".":
            return "start_forward"
        if key == "<":
            return "end_backward"
        if key == ">":
            return "end_forward"
        return "other"
    except (EOFError, OSError) as exc:
        raise RuntimeError("Unable to read keys; run auto_miner in an interactive terminal.") from exc


def _clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _edit_translation(initial: str) -> str:
    """Edit a translation in-place, returning the original value on Escape."""
    if os.name != "nt":
        raise RuntimeError("auto_miner requires a Windows interactive terminal for translation editing.")
    import msvcrt

    value = list(initial)
    cursor = len(value)
    prompt = "Edit back: "

    def redraw() -> None:
        rendered = "".join(value)
        sys.stdout.write(f"\r{prompt}{rendered}\033[K")
        distance_from_end = len(value) - cursor
        if distance_from_end:
            sys.stdout.write(f"\033[{distance_from_end}D")
        sys.stdout.flush()

    print("Edit the proposed translation. Enter: save edit   Esc: cancel edit")
    redraw()
    while True:
        key = msvcrt.getwch()
        if key == "\r":
            print()
            return "".join(value)
        if key == "\x1b":
            print()
            return initial
        if key in ("\x08", "\x7f"):
            if cursor:
                del value[cursor - 1]
                cursor -= 1
                redraw()
            continue
        if key in ("\x00", "\xe0"):
            command = msvcrt.getwch()
            if command == "K":
                cursor = max(0, cursor - 1)
            elif command == "M":
                cursor = min(len(value), cursor + 1)
            elif command == "G":
                cursor = 0
            elif command == "O":
                cursor = len(value)
            elif command == "S" and cursor < len(value):
                del value[cursor]
            redraw()
            continue
        if key.isprintable():
            value.insert(cursor, key)
            cursor += 1
            redraw()


EDITOR_HEADER_LINE_COUNT = 3


def _decode_editor_key(getwch: Callable[[], str]) -> str:
    """Read one keystroke and resolve it to an editor key name or literal character."""
    key = getwch()
    if key in ("\x00", "\xe0"):
        command = getwch()
        return {
            "K": "left",
            "M": "right",
            "H": "up",
            "P": "down",
            "G": "home",
            "O": "end",
            "S": "delete",
        }.get(command, "")
    if key == "\r":
        return "enter"
    if key in ("\x08", "\x7f"):
        return "backspace"
    if key == "\x13":
        return "save"
    return key


def _apply_editor_key(
    lines: list[str], row: int, col: int, key: str
) -> tuple[list[str], int, int]:
    """Apply one editor key to the text buffer, returning the updated buffer and cursor."""
    if key == "enter":
        current = lines[row]
        lines[row : row + 1] = [current[:col], current[col:]]
        return lines, row + 1, 0
    if key == "backspace":
        if col > 0:
            lines[row] = lines[row][: col - 1] + lines[row][col:]
            return lines, row, col - 1
        if row > 0:
            merged_col = len(lines[row - 1])
            lines[row - 1] += lines[row]
            del lines[row]
            return lines, row - 1, merged_col
        return lines, row, col
    if key == "delete":
        if col < len(lines[row]):
            lines[row] = lines[row][:col] + lines[row][col + 1 :]
        elif row < len(lines) - 1:
            lines[row] += lines[row + 1]
            del lines[row + 1]
        return lines, row, col
    if key == "left":
        if col > 0:
            return lines, row, col - 1
        if row > 0:
            return lines, row - 1, len(lines[row - 1])
        return lines, row, col
    if key == "right":
        if col < len(lines[row]):
            return lines, row, col + 1
        if row < len(lines) - 1:
            return lines, row + 1, 0
        return lines, row, col
    if key == "up":
        if row > 0:
            return lines, row - 1, min(col, len(lines[row - 1]))
        return lines, row, col
    if key == "down":
        if row < len(lines) - 1:
            return lines, row + 1, min(col, len(lines[row + 1]))
        return lines, row, col
    if key == "home":
        return lines, row, 0
    if key == "end":
        return lines, row, len(lines[row])
    if len(key) == 1 and key.isprintable():
        lines[row] = lines[row][:col] + key + lines[row][col:]
        return lines, row, col + 1
    return lines, row, col


def _move_cursor(row: int, col: int) -> None:
    sys.stdout.write(f"\033[{row};{col}H")
    sys.stdout.flush()


def edit_input_file(
    path: Path,
    *,
    read_key: Callable[[], str] | None = None,
    print_fn: Callable[..., None] = print,
    clear_screen: Callable[[], None] = _clear_screen,
    move_cursor: Callable[[int, int], None] = _move_cursor,
) -> None:
    """Open a terminal editor pre-filled with *path*'s contents; Ctrl+S saves and returns."""
    if read_key is None:
        if os.name != "nt":
            raise RuntimeError("auto_miner requires a Windows interactive terminal to edit the queue.")
        import msvcrt

        read_key = lambda: _decode_editor_key(msvcrt.getwch)

    initial = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
    lines = initial.split("\n") if initial else [""]
    row, col = len(lines) - 1, len(lines[-1])

    def redraw() -> None:
        clear_screen()
        print_fn("Edit automine_inputs.txt — '# <path or URL>' starts a source; one phrase to mine per line below it.")
        print_fn("Arrows: move   Enter: new line   Backspace: delete   Ctrl+S: save and start mining")
        print_fn()
        for line in lines:
            print_fn(line)
        move_cursor(EDITOR_HEADER_LINE_COUNT + row + 1, col + 1)

    redraw()
    while True:
        key = read_key()
        if key == "save":
            break
        lines, row, col = _apply_editor_key(lines, row, col, key)
        redraw()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _display_front(candidate: MiningCandidate, context: str) -> str:
    highlighted = f"\033[31m[{candidate.matched_text}]\033[0m"
    return context.replace(candidate.matched_text, highlighted, 1)


def _display_context_window(candidate: MiningCandidate, bounds: tuple[int, int]) -> str:
    """Render the active context and five dimmed source words on each side."""
    before, after = render_context_neighbor_words(candidate, bounds)
    context = render_context_window(candidate, bounds)
    gray = "\033[90m"
    reset = "\033[0m"
    parts = []
    if before:
        parts.append(f"{gray}{before}{reset}")
    parts.append(_display_front(candidate, context))
    if after:
        parts.append(f"{gray}{after}{reset}")
    return " ".join(parts)


def _display_width(text: str) -> int:
    """Return terminal columns occupied by text, ignoring ANSI formatting."""
    width = 0
    for character in ANSI_ESCAPE_PATTERN.sub("", text):
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"F", "W"} else 1
    return width


def _wrap_card_text(text: str, width: int) -> list[str]:
    """Wrap ANSI-styled text without counting its escape sequences as columns."""
    lines: list[str] = []
    line = ""
    line_width = 0
    pending_space = False
    tokens = re.findall(r"\x1b\[[0-?]*[ -/]*[@-~]|\s+|[^\s]", text)

    for token in tokens:
        if ANSI_ESCAPE_PATTERN.fullmatch(token):
            line += token
            continue
        if token.isspace():
            pending_space = bool(line)
            continue

        character_width = _display_width(token)
        separator_width = 1 if pending_space and line_width else 0
        if line_width and line_width + separator_width + character_width > width:
            lines.append(line)
            line = ""
            line_width = 0
            pending_space = False
            separator_width = 0
        if pending_space and line_width:
            line += " "
            line_width += 1
        line += token
        line_width += character_width
        pending_space = False

    if line or not lines:
        lines.append(line)
    return lines


def _card_content_width(front: str, back: str) -> int:
    """Choose a readable card width that stays within the current terminal."""
    terminal_width = shutil.get_terminal_size(fallback=(80, 24)).columns
    maximum = min(CARD_MAX_CONTENT_WIDTH, max(20, terminal_width - 4))
    minimum = min(CARD_MIN_CONTENT_WIDTH, maximum)
    longest_line = max(
        (_display_width(line) for text in (front, back) for line in text.splitlines()),
        default=0,
    )
    return min(maximum, max(minimum, longest_line))


def render_anki_card_preview(front: str, back: str) -> str:
    """Render the proposed front and back as a compact terminal Anki card."""
    content_width = _card_content_width(front, back)
    border = "-" * (content_width + 4)
    lines = [border]
    for label, text in (("front", front), ("back", back)):
        lines.extend(f"| {' ' * content_width} |" for _ in range(CARD_VERTICAL_PADDING))
        for content_line in _wrap_card_text(f"{label}: {text}", content_width):
            padding = " " * (content_width - _display_width(content_line))
            lines.append(f"| {content_line}{padding} |")
        lines.extend(f"| {' ' * content_width} |" for _ in range(CARD_VERTICAL_PADDING))
    lines.append(border)
    return "\n".join(lines)


def review_candidates(
    candidates: list[MiningCandidate],
    translate: Callable[[str], str],
    add_card: Callable[[str, str, str], object],
    *,
    read_key: Callable[[], str] = _read_key,
    edit_translation: Callable[[str], str] = _edit_translation,
    print_fn: Callable[..., None] = print,
    clear_screen: Callable[[], None] = _clear_screen,
    queue_position: int | None = None,
    queue_total: int | None = None,
) -> bool:
    """Review candidates and add the approved card. Return True when approved."""
    selected = 0
    bounds_by_candidate = [context_window_bounds(candidate) for candidate in candidates]
    translations: dict[str, str] = {}
    while True:
        candidate = candidates[selected]
        bounds = bounds_by_candidate[selected]
        context = render_context_window(candidate, bounds)
        if candidate.matched_text not in translations:
            translations[candidate.matched_text] = translate(candidate.matched_text)
        clear_screen()
        print_fn(
            render_anki_card_preview(
                _display_context_window(candidate, bounds),
                translations[candidate.matched_text],
            )
        )
        print_fn()
        print_fn(f"Source: {candidate.source_name} {candidate.location}")
        if queue_position is not None and queue_total is not None:
            print_fn(f"Queue: word {queue_position} of {queue_total}")
        if len(candidates) > 1:
            print_fn(f"\n{selected + 1} of {len(candidates)} — Left/Right: choose occurrence")
        print_fn(
            "Enter: create card   E: edit translation   Esc: skip\n"
            ", / .: move context start   < / >: move context end"
        )
        key = read_key()
        if key == "enter":
            add_card(context, candidate.matched_text, translations[candidate.matched_text])
            return True
        if key == "escape":
            return False
        if key == "e":
            translations[candidate.matched_text] = edit_translation(translations[candidate.matched_text])
        if key in {"start_backward", "start_forward", "end_backward", "end_forward"}:
            bounds_by_candidate[selected] = adjust_context_window(candidate, bounds, key)
        if key == "left" and len(candidates) > 1:
            selected = (selected - 1) % len(candidates)
        if key == "right" and len(candidates) > 1:
            selected = (selected + 1) % len(candidates)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not sys.stdin.isatty():
        print("Error: auto_miner must be run in an interactive terminal.", file=sys.stderr)
        return 1
    try:
        edit_input_file(args.input_file)
        sections = load_queue_sections(args.input_file)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not sections:
        print("No '# <source>' sections with phrases found in the input file.", file=sys.stderr)
        return 1
    try:
        started_anki = start_anki_if_needed()
    except (ConnectionError, FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if started_anki:
        print("Started Anki and connected to AnkiConnect.")
    if not test_anki_connection():
        print("Error: AnkiConnect, the LinguaLoop deck, or the Basic model is unavailable.", file=sys.stderr)
        return 1

    translator = FallbackTranslator(
        OnlineTranslationBackend(),
        MarianMTTranslationBackend(),
        online_source_code=get_google_language_code(args.source_lang),
        online_target_code=get_google_language_code(args.target_lang),
        offline_source_code=get_marian_language_code(args.source_lang),
        offline_target_code=get_marian_language_code(args.target_lang),
    )

    approved = skipped = unmatched = 0
    for section in sections:
        print(f"\nSource: {section.source}", flush=True)
        if is_inline_source(section.source):
            candidates_by_query = [inline_candidates(query) for query in section.queries]
        else:
            try:
                contexts = load_source_contexts(section.source)
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                print(f"Skipping source: {exc}", file=sys.stderr)
                continue
            if not contexts:
                print("Skipping source: no readable text contexts found.", file=sys.stderr)
                continue

            print("Finding word instances...", flush=True)
            candidates_by_query = find_all_candidates(section.queries, contexts)
            print("Word-instance search complete.", flush=True)

        for queue_position, (query, candidates) in enumerate(
            zip(section.queries, candidates_by_query), start=1
        ):
            if not candidates:
                unmatched += 1
                print(f"No match: {query}")
                continue
            try:
                created = review_candidates(
                    candidates,
                    translator.translate,
                    add_anki_card,
                    queue_position=queue_position,
                    queue_total=len(section.queries),
                )
                if created:
                    remove_section_query_from_queue(args.input_file, section.source, query)
            except Exception as exc:
                print(f"Error while processing '{query}': {exc}", file=sys.stderr)
                return 1
            if created:
                approved += 1
            else:
                skipped += 1

    print(f"Finished: {approved} created, {skipped} skipped, {unmatched} unmatched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
