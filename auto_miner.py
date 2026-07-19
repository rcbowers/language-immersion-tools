#!/usr/bin/env python3
"""Interactively mine phrases from PDF or SRT sources into LinguaLoop Anki cards."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Callable, Iterable, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from immersion_app.core.anki import add_anki_card, test_anki_connection
from immersion_app.core.auto_mining import MiningCandidate, MiningContext, find_candidates
from immersion_app.core.language_config import SUPPORTED_LANGUAGES, get_google_language_code
from immersion_app.integrations.translation_backends import OnlineTranslationBackend
from immersion_app.media.source_context import load_source_contexts


DEFAULT_INPUT_FILE = "automine_inputs.txt"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="SOURCE_DOCUMENT, or INPUT_FILE SOURCE_DOCUMENT",
    )
    parser.add_argument("--source-lang", default="es", choices=sorted(SUPPORTED_LANGUAGES))
    parser.add_argument("--target-lang", default="en", choices=sorted(SUPPORTED_LANGUAGES))
    args = parser.parse_args(argv)
    if len(args.paths) == 1:
        args.input_file = Path(DEFAULT_INPUT_FILE)
        args.source_document = Path(args.paths[0])
    elif len(args.paths) == 2:
        args.input_file = Path(args.paths[0])
        args.source_document = Path(args.paths[1])
    else:
        parser.error("Use SOURCE_DOCUMENT or INPUT_FILE SOURCE_DOCUMENT.")
    return args


def load_queries(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


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


def _display_front(candidate: MiningCandidate) -> str:
    highlighted = f"\033[31m[{candidate.matched_text}]\033[0m"
    return candidate.sentence.replace(candidate.matched_text, highlighted, 1)


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
    translations: dict[str, str] = {}
    while True:
        candidate = candidates[selected]
        if candidate.matched_text not in translations:
            translations[candidate.matched_text] = translate(candidate.matched_text)
        clear_screen()
        print_fn(f"front: {_display_front(candidate)}")
        print_fn(f"back: {translations[candidate.matched_text]}")
        print_fn()
        print_fn(f"Source: {candidate.source_name} {candidate.location}")
        if queue_position is not None and queue_total is not None:
            print_fn(f"Queue: word {queue_position} of {queue_total}")
        if len(candidates) > 1:
            print_fn(f"\n{selected + 1} of {len(candidates)} — Left/Right: choose occurrence")
        print_fn("Enter: create card   E: edit translation   Esc: skip")
        key = read_key()
        if key == "enter":
            add_card(candidate.sentence, candidate.matched_text, translations[candidate.matched_text])
            return True
        if key == "escape":
            return False
        if key == "e":
            translations[candidate.matched_text] = edit_translation(translations[candidate.matched_text])
        if key == "left" and len(candidates) > 1:
            selected = (selected - 1) % len(candidates)
        if key == "right" and len(candidates) > 1:
            selected = (selected + 1) % len(candidates)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        queries = load_queries(args.input_file)
        contexts = load_source_contexts(args.source_document)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not queries:
        print("No phrases found in the input file.", file=sys.stderr)
        return 1
    if not contexts:
        print("No readable text contexts found in the source document.", file=sys.stderr)
        return 1
    if not sys.stdin.isatty():
        print("Error: auto_miner must be run in an interactive terminal.", file=sys.stderr)
        return 1
    if not test_anki_connection():
        print("Error: AnkiConnect, the LinguaLoop deck, or the Basic model is unavailable.", file=sys.stderr)
        return 1

    backend = OnlineTranslationBackend()
    source_code = get_google_language_code(args.source_lang)
    target_code = get_google_language_code(args.target_lang)
    print("Finding word instances...", flush=True)
    candidates_by_query = find_all_candidates(queries, contexts)
    print("Word-instance search complete.", flush=True)

    approved = skipped = unmatched = 0
    for queue_position, (query, candidates) in enumerate(zip(queries, candidates_by_query), start=1):
        if not candidates:
            unmatched += 1
            print(f"No match: {query}")
            continue
        try:
            created = review_candidates(
                candidates,
                lambda text: backend.translate(text, source_code, target_code),
                add_anki_card,
                queue_position=queue_position,
                queue_total=len(queries),
            )
            if created:
                remove_query_from_queue(args.input_file, query)
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
