#!/usr/bin/env python3
"""
Spanish Sentence Mining Automation Script
Processes Spanish sentences with target words and creates Anki flashcards
using the AnkiConnect API.
"""

import json
import urllib.request
import urllib.error
import re
from datetime import datetime
from pathlib import Path


# Configuration
INPUT_FILE = "words_to_process.txt"
PROCESSED_FILE = "processed_words.txt"
DECK_NAME = "2025 Spanish Immersion"
MODEL_NAME = "Basic"
ANKI_CONNECT_URL = "http://localhost:8765"


def anki_connect_request(action, **params):
    """Create an AnkiConnect request."""
    return {'action': action, 'version': 6, 'params': params}


def anki_connect_invoke(action, **params):
    """Invoke an AnkiConnect action and return the result."""
    request_json = json.dumps(anki_connect_request(action, **params)).encode('utf-8')

    try:
        response = json.load(urllib.request.urlopen(
            urllib.request.Request(ANKI_CONNECT_URL, request_json)
        ))
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"Failed to connect to AnkiConnect at {ANKI_CONNECT_URL}. "
            "Make sure Anki is running and AnkiConnect add-on is installed."
        ) from e

    if len(response) != 2:
        raise Exception('Response has an unexpected number of fields')
    if 'error' not in response:
        raise Exception('Response is missing required error field')
    if 'result' not in response:
        raise Exception('Response is missing required result field')
    if response['error'] is not None:
        raise Exception(f"AnkiConnect error: {response['error']}")

    return response['result']


def test_anki_connection():
    """Test if AnkiConnect is available and the deck exists."""
    print("Testing connection to Anki...")

    # Test basic connection
    try:
        version = anki_connect_invoke('version')
        print(f"✓ Connected to AnkiConnect (version {version})")
    except ConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return False

    # Check if deck exists
    deck_names = anki_connect_invoke('deckNames')
    if DECK_NAME not in deck_names:
        print(f"✗ Deck '{DECK_NAME}' not found in Anki")
        print(f"  Available decks: {', '.join(deck_names)}")
        return False
    else:
        print(f"✓ Deck '{DECK_NAME}' found")

    # Check if model exists
    model_names = anki_connect_invoke('modelNames')
    if MODEL_NAME not in model_names:
        print(f"✗ Model '{MODEL_NAME}' not found in Anki")
        print(f"  Available models: {', '.join(model_names)}")
        return False
    else:
        print(f"✓ Model '{MODEL_NAME}' found")

    return True


def highlight_word_in_sentence(sentence, target_word):
    """Highlight the target word in the sentence with red color."""
    # Escape HTML special characters in the sentence and word
    sentence_escaped = sentence.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    target_word_escaped = target_word.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Create a pattern for case-insensitive matching, escaping regex special chars
    pattern = re.escape(target_word_escaped)

    # Replace with highlighted version (case-insensitive)
    highlighted = re.sub(
        f'({pattern})',
        r'<span style="color: red;">\1</span>',
        sentence_escaped,
        flags=re.IGNORECASE
    )

    return highlighted


def add_anki_card(spanish_sentence, target_word, english_translation):
    """Add a card to Anki using AnkiConnect."""
    # Highlight the target word in red
    front_content = highlight_word_in_sentence(spanish_sentence, target_word)
    back_content = english_translation

    note = {
        "deckName": DECK_NAME,
        "modelName": MODEL_NAME,
        "fields": {
            "Front": front_content,
            "Back": back_content
        },
        "tags": ["sentence-mining", "auto-generated"]
    }

    result = anki_connect_invoke('addNote', note=note)
    return result


def parse_input_file(filepath):
    """Parse the input file and return a list of entries."""
    if not Path(filepath).exists():
        raise FileNotFoundError(f"Input file '{filepath}' not found")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = []
    lines = content.strip().split('\n')

    i = 0
    while i < len(lines):
        # Skip empty lines
        if not lines[i].strip():
            i += 1
            continue

        # Try to read three lines for an entry
        if i + 2 < len(lines):
            spanish_sentence = lines[i].strip()
            target_word = lines[i + 1].strip()
            english_translation = lines[i + 2].strip()

            if spanish_sentence and target_word and english_translation:
                entries.append({
                    'sentence': spanish_sentence,
                    'word': target_word,
                    'translation': english_translation
                })
                i += 3
            else:
                print(f"Warning: Skipping incomplete entry at line {i + 1}")
                i += 1
        else:
            print(f"Warning: Incomplete entry at end of file (line {i + 1})")
            break

    return entries


def append_to_processed_file(entries):
    """Append processed words to the processed_words.txt file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(PROCESSED_FILE, 'a', encoding='utf-8') as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"Batch processed on: {timestamp}\n")
        f.write(f"{'='*60}\n\n")

        for entry in entries:
            entry_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{entry_time}] {entry['word']} - {entry['translation']}\n")
            f.write(f"  Sentence: {entry['sentence']}\n\n")


def rewrite_input_file(entries):
    """Rewrite the input file with only the remaining (failed) entries."""
    if not entries:
        # If no entries remain, clear the file
        with open(INPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("")
        return

    # Write remaining entries back to file
    with open(INPUT_FILE, 'w', encoding='utf-8') as f:
        for i, entry in enumerate(entries):
            f.write(f"{entry['sentence']}\n")
            f.write(f"{entry['word']}\n")
            f.write(f"{entry['translation']}\n")
            # Add blank line between entries, but not after the last one
            if i < len(entries) - 1:
                f.write("\n")


def main():
    """Main function to process sentences and create Anki cards."""
    print("="*60)
    print("Spanish Sentence Mining - Anki Card Creator")
    print("="*60)
    print()

    # Test Anki connection
    if not test_anki_connection():
        print("\nExiting: Please fix the issues above and try again.")
        return

    print()

    # Parse input file
    try:
        entries = parse_input_file(INPUT_FILE)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    if not entries:
        print(f"No valid entries found in '{INPUT_FILE}'")
        return

    print(f"Found {len(entries)} entries to process\n")

    # Process each entry
    successful_entries = []
    failed_entries = []
    sentence_counts = {}  # Track duplicate sentences

    for idx, entry in enumerate(entries, 1):
        try:
            print(f"[{idx}/{len(entries)}] Processing: {entry['word']}", end=" ... ")

            # Check for duplicate sentences and append suffix if needed
            sentence = entry['sentence']
            if sentence in sentence_counts:
                sentence_counts[sentence] += 1
                sentence_with_suffix = f"{sentence} ({sentence_counts[sentence]})"
            else:
                sentence_counts[sentence] = 1
                sentence_with_suffix = sentence

            note_id = add_anki_card(
                sentence_with_suffix,
                entry['word'],
                entry['translation']
            )

            print(f"✓ Added (Note ID: {note_id})")
            successful_entries.append(entry)

        except Exception as e:
            print(f"✗ Failed: {e}")
            failed_entries.append(entry)

    print()
    print("="*60)
    print(f"Processing complete!")
    print(f"  Successful: {len(successful_entries)}")
    print(f"  Failed: {len(failed_entries)}")
    print("="*60)

    # Append to processed file
    if successful_entries:
        try:
            append_to_processed_file(successful_entries)
            print(f"\nProcessed words logged to '{PROCESSED_FILE}'")
        except Exception as e:
            print(f"\nWarning: Failed to update processed file: {e}")

    # Remove successfully processed entries from input file
    if successful_entries:
        try:
            rewrite_input_file(failed_entries)
            if failed_entries:
                print(f"'{INPUT_FILE}' updated - {len(successful_entries)} entries removed, {len(failed_entries)} remaining")
            else:
                print(f"'{INPUT_FILE}' cleared - all entries processed successfully")
        except Exception as e:
            print(f"\nWarning: Failed to update input file: {e}")
            print(f"You may need to manually remove processed entries from '{INPUT_FILE}'")

    print()
    print("Next steps:")
    print(f"1. Check your '{DECK_NAME}' deck in Anki")
    if failed_entries:
        print(f"2. Review and fix the {len(failed_entries)} failed entries in '{INPUT_FILE}'")
    print()


if __name__ == "__main__":
    main()
