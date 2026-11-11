#!/usr/bin/env python3
"""
anki_vocab_count.py

Count unique lexical lemmas in an Anki deck using AnkiConnect and spaCy.

Examples:
    python anki_vocab_count.py "Spanish Mining" es
    python anki_vocab_count.py "Spanish Mining" spanish --fields Sentence
    python anki_vocab_count.py "Spanish Mining" es --show-words
    python anki_vocab_count.py "Spanish Mining" es --output vocab.csv

Requirements:
    pip install requests spacy beautifulsoup4 matplotlib

Then install the appropriate spaCy model, for example:
    python -m spacy download es_core_news_sm
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

import requests
import spacy
from bs4 import BeautifulSoup

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ANKI_CONNECT_URL = "http://127.0.0.1:8765"
ANKI_CONNECT_VERSION = 6
NOTE_BATCH_SIZE = 500


LANGUAGES = {
    "en": {
        "name": "English",
        "aliases": {"en", "english"},
        "model": "en_core_web_sm",
    },
    "es": {
        "name": "Spanish",
        "aliases": {"es", "spanish", "español", "espanol"},
        "model": "es_core_news_sm",
    },
    "fr": {
        "name": "French",
        "aliases": {"fr", "french", "français", "francais"},
        "model": "fr_core_news_sm",
    },
    "de": {
        "name": "German",
        "aliases": {"de", "german", "deutsch"},
        "model": "de_core_news_sm",
    },
    "it": {
        "name": "Italian",
        "aliases": {"it", "italian", "italiano"},
        "model": "it_core_news_sm",
    },
    "pt": {
        "name": "Portuguese",
        "aliases": {"pt", "portuguese", "português", "portugues"},
        "model": "pt_core_news_sm",
    },
    "nl": {
        "name": "Dutch",
        "aliases": {"nl", "dutch", "nederlands"},
        "model": "nl_core_news_sm",
    },
    "ja": {
        "name": "Japanese",
        "aliases": {"ja", "japanese", "日本語"},
        "model": "ja_core_news_sm",
    },
    "zh": {
        "name": "Chinese",
        "aliases": {"zh", "chinese", "中文"},
        "model": "zh_core_web_sm",
    },
}


SOUND_RE = re.compile(r"\[sound:[^\]]+\]", re.IGNORECASE)

# {{c1::word}}       -> word
# {{c1::word::hint}} -> word
CLOZE_RE = re.compile(
    r"\{\{c\d+::(.*?)(?:::[^}]*)?\}\}",
    flags=re.IGNORECASE | re.DOTALL,
)

ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")


class AnkiConnectError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Count unique words/lemmas in an Anki deck using "
            "AnkiConnect and spaCy."
        )
    )

    parser.add_argument(
        "deck",
        help="Name of the Anki deck to analyze.",
    )

    parser.add_argument(
        "language",
        help="Language name or code, e.g. es, spanish, en, french.",
    )

    parser.add_argument(
        "--fields",
        nargs="+",
        metavar="FIELD",
        help=(
            "Only analyze these note fields. "
            "By default, all fields are analyzed."
        ),
    )

    parser.add_argument(
        "--show-words",
        action="store_true",
        help="Print every counted lemma and its frequency.",
    )

    parser.add_argument(
        "--output",
        metavar="FILE",
        help=(
            "Write the vocabulary list to a file. "
            ".csv files are written as CSV; other extensions use TSV."
        ),
    )

    parser.add_argument(
        "--include-proper-nouns",
        action="store_true",
        help="Include proper nouns such as names and places.",
    )

    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        metavar="N",
        help="Only count lemmas appearing at least N times. Default: 1.",
    )

    parser.add_argument(
        "--url",
        default=ANKI_CONNECT_URL,
        help=f"AnkiConnect URL. Default: {ANKI_CONNECT_URL}",
    )

    args = parser.parse_args()

    if args.min_count < 1:
        parser.error("--min-count must be at least 1")

    return args


def resolve_language(language_input: str) -> tuple[str, dict]:
    value = language_input.strip().casefold()

    for code, config in LANGUAGES.items():
        aliases = {alias.casefold() for alias in config["aliases"]}

        if value == code or value in aliases:
            return code, config

    supported = ", ".join(
        f"{code} ({config['name']})"
        for code, config in LANGUAGES.items()
    )

    raise ValueError(
        f"Unsupported language: {language_input}\n"
        f"Supported languages: {supported}"
    )


def anki_request(
    url: str,
    action: str,
    params: dict | None = None,
):
    payload = {
        "action": action,
        "version": ANKI_CONNECT_VERSION,
        "params": params or {},
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise AnkiConnectError(
            f"Could not connect to AnkiConnect at {url}.\n\n"
            "Make sure:\n"
            "  1. Anki is running.\n"
            "  2. The AnkiConnect add-on is installed.\n"
            f"  3. AnkiConnect is listening at {url}."
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise AnkiConnectError(
            "AnkiConnect returned an invalid JSON response."
        ) from exc

    if data.get("error") is not None:
        raise AnkiConnectError(
            f"AnkiConnect error while calling '{action}': "
            f"{data['error']}"
        )

    return data.get("result")


def verify_ankiconnect(url: str) -> None:
    version = anki_request(url, "version")

    if not isinstance(version, int):
        raise AnkiConnectError(
            f"Unexpected AnkiConnect version response: {version!r}"
        )


def get_deck_names(url: str) -> list[str]:
    result = anki_request(url, "deckNames")

    if not isinstance(result, list):
        raise AnkiConnectError(
            "Unexpected response from AnkiConnect deckNames."
        )

    return result


def escape_anki_search_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def get_note_ids(url: str, deck_name: str) -> list[int]:
    safe_deck_name = escape_anki_search_string(deck_name)
    query = f'deck:"{safe_deck_name}"'

    result = anki_request(
        url,
        "findNotes",
        {"query": query},
    )

    if not isinstance(result, list):
        raise AnkiConnectError(
            "Unexpected response from AnkiConnect findNotes."
        )

    return result


def chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def get_notes(url: str, note_ids: list[int]) -> list[dict]:
    notes = []

    for batch in chunks(note_ids, NOTE_BATCH_SIZE):
        result = anki_request(
            url,
            "notesInfo",
            {"notes": batch},
        )

        if not isinstance(result, list):
            raise AnkiConnectError(
                "Unexpected response from AnkiConnect notesInfo."
            )

        notes.extend(result)

    return notes


def load_language_model(config: dict):
    model_name = config["model"]

    try:
        return spacy.load(
            model_name,
            disable=["ner"],
        )
    except OSError as exc:
        raise RuntimeError(
            f"{config['name']} spaCy model '{model_name}' "
            "is not installed.\n\n"
            "Install it with:\n\n"
            f"    python -m spacy download {model_name}"
        ) from exc


def clean_text(value: str) -> str:
    if not value:
        return ""

    # Remove Anki sound references.
    text = SOUND_RE.sub(" ", value)

    # Preserve the visible portion of cloze deletions.
    text = CLOZE_RE.sub(r"\1", text)

    # Strip HTML while preserving boundaries between elements.
    text = BeautifulSoup(text, "html.parser").get_text(" ")

    # Remove zero-width Unicode characters.
    text = ZERO_WIDTH_RE.sub("", text)

    # Normalize whitespace.
    text = " ".join(text.split())

    return text


def extract_texts(
    notes: list[dict],
    requested_fields: list[str] | None,
) -> tuple[list[str], int, set[str]]:
    texts = []
    fields_processed = 0
    fields_found = set()

    for note in notes:
        note_fields = note.get("fields", {})

        if requested_fields:
            field_names = requested_fields
        else:
            field_names = list(note_fields.keys())

        for field_name in field_names:
            field = note_fields.get(field_name)

            if field is None:
                continue

            fields_found.add(field_name)

            value = field.get("value", "")
            cleaned = clean_text(value)

            if cleaned:
                texts.append(cleaned)
                fields_processed += 1

    return texts, fields_processed, fields_found


def is_valid_token(
    token,
    include_proper_nouns: bool,
) -> bool:
    if token.is_space:
        return False

    if token.is_punct:
        return False

    if token.like_num:
        return False

    if token.like_url:
        return False

    if token.like_email:
        return False

    # Removes punctuation, symbols, mixed strings, etc.
    if not token.is_alpha:
        return False

    if not include_proper_nouns and token.pos_ == "PROPN":
        return False

    return True


def normalize_token(token) -> str | None:
    lemma = token.lemma_.strip()

    # Some pipelines or unusual tokens may not provide a useful lemma.
    if not lemma or lemma == "-PRON-":
        lemma = token.text.strip()

    lemma = lemma.casefold()

    if not lemma:
        return None

    return lemma


def analyze_texts(
    texts: list[str],
    nlp,
    include_proper_nouns: bool,
) -> tuple[Counter, int, int]:
    frequencies = Counter()

    total_tokens = 0
    valid_word_tokens = 0

    # nlp.pipe() is much faster than calling nlp(text) repeatedly.
    for doc in nlp.pipe(texts, batch_size=64):
        total_tokens += len(doc)

        for token in doc:
            if not is_valid_token(
                token,
                include_proper_nouns=include_proper_nouns,
            ):
                continue

            lemma = normalize_token(token)

            if lemma is None:
                continue

            frequencies[lemma] += 1
            valid_word_tokens += 1

    return frequencies, total_tokens, valid_word_tokens


def filter_frequencies(
    frequencies: Counter,
    min_count: int,
) -> dict[str, int]:
    return {
        lemma: count
        for lemma, count in frequencies.items()
        if count >= min_count
    }


def write_output(
    output_path: str,
    frequencies: dict[str, int],
) -> None:
    path = Path(output_path)

    rows = sorted(
        frequencies.items(),
        key=lambda item: item[0],
    )

    try:
        with path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:
            if path.suffix.casefold() == ".csv":
                writer = csv.writer(file)
                writer.writerow(["lemma", "count"])
                writer.writerows(rows)
            else:
                writer = csv.writer(file, delimiter="\t")
                writer.writerow(["lemma", "count"])
                writer.writerows(rows)

    except OSError as exc:
        raise RuntimeError(
            f"Could not write output file: {path}"
        ) from exc


def print_words(frequencies: dict[str, int]) -> None:
    print()
    print("Vocabulary:")
    print()

    for lemma, count in sorted(
        frequencies.items(),
        key=lambda item: item[0],
    ):
        print(f"{lemma}\t{count}")


def plot_filename(deck_name: str) -> Path:
    """Return a safe default filename for a deck's distribution plot."""
    safe_deck_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", deck_name)
    safe_deck_name = re.sub(r"\s+", "_", safe_deck_name).strip("._")

    if not safe_deck_name:
        safe_deck_name = "deck"

    return Path(f"{safe_deck_name}_word_distribution.png")


def create_word_distribution_plot(
    frequencies: dict[str, int],
    output_path: Path,
) -> bool:
    """Save a descending word-frequency bar chart and report success."""
    if not frequencies:
        print("No words to plot.")
        return False

    sorted_frequencies = sorted(
        frequencies.items(),
        key=lambda item: (-item[1], item[0]),
    )
    words, instances = zip(*sorted_frequencies)
    figure_width = max(12, min(60, len(words) * 0.35))

    figure, axis = plt.subplots(figsize=(figure_width, 8))
    axis.bar(range(len(words)), instances, color="steelblue")
    axis.set_xlabel("Word")
    axis.set_ylabel("Instances")
    axis.set_title("Word Distribution")
    axis.set_xticks(range(len(words)))
    axis.set_xticklabels(words, rotation=45, ha="right", fontsize=8)
    axis.grid(axis="y", alpha=0.3)
    figure.tight_layout()

    try:
        figure.savefig(output_path, dpi=200, bbox_inches="tight")
    except OSError as exc:
        raise RuntimeError(
            f"Could not write word distribution plot: {output_path}"
        ) from exc
    finally:
        plt.close(figure)

    return True


def main() -> int:
    args = parse_args()

    try:
        _, language_config = resolve_language(args.language)

        print(f"Loading {language_config['name']} language model...")
        nlp = load_language_model(language_config)

        print("Connecting to Anki...")
        verify_ankiconnect(args.url)

        deck_names = get_deck_names(args.url)

        if args.deck not in deck_names:
            print(
                f'ERROR: Anki deck "{args.deck}" does not exist.',
                file=sys.stderr,
            )
            return 1

        print(f'Retrieving notes from "{args.deck}"...')
        note_ids = get_note_ids(args.url, args.deck)

        if not note_ids:
            print()
            print(f"Deck: {args.deck}")
            print(f"Language: {language_config['name']}")
            print()
            print("Notes processed:       0")
            print("Text fields processed: 0")
            print("Tokens processed:      0")
            print("Word tokens:           0")
            print("Unique words:          0")
            return 0

        notes = get_notes(args.url, note_ids)

        texts, fields_processed, fields_found = extract_texts(
            notes,
            args.fields,
        )

        if args.fields:
            missing_fields = [
                field
                for field in args.fields
                if field not in fields_found
            ]

            if missing_fields:
                available_fields = sorted(
                    {
                        field_name
                        for note in notes
                        for field_name in note.get("fields", {})
                    }
                )

                print(
                    "ERROR: The following requested fields were "
                    "not found:",
                    file=sys.stderr,
                )

                for field in missing_fields:
                    print(f"  {field}", file=sys.stderr)

                if available_fields:
                    print(
                        "\nAvailable fields:",
                        file=sys.stderr,
                    )
                    for field in available_fields:
                        print(f"  {field}", file=sys.stderr)

                return 1

        print("Analyzing vocabulary...")

        frequencies, total_tokens, valid_word_tokens = analyze_texts(
            texts,
            nlp,
            include_proper_nouns=args.include_proper_nouns,
        )

        filtered = filter_frequencies(
            frequencies,
            args.min_count,
        )

        print()
        print(f"Deck: {args.deck}")
        print(f"Language: {language_config['name']}")
        print()
        print(f"Notes processed:       {len(notes):,}")
        print(f"Text fields processed: {fields_processed:,}")
        print(f"Tokens processed:      {total_tokens:,}")
        print(f"Word tokens:           {valid_word_tokens:,}")

        if args.min_count == 1:
            print(f"Unique words:          {len(filtered):,}")
        else:
            print(
                f"Unique words "
                f"(appearing >= {args.min_count} times): "
                f"{len(filtered):,}"
            )

        if args.output:
            write_output(args.output, filtered)
            print()
            print(f"Vocabulary written to: {args.output}")

        if args.show_words:
            print_words(filtered)

        distribution_plot = plot_filename(args.deck)
        if create_word_distribution_plot(filtered, distribution_plot):
            print()
            print(f"Word distribution plot written to: {distribution_plot}")

        return 0

    except (
        ValueError,
        RuntimeError,
        AnkiConnectError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
