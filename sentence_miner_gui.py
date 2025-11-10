#!/usr/bin/env python3
"""
Spanish Sentence Mining GUI Tool
A tkinter-based GUI for creating Spanish Anki flashcards with automatic translation.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import re
from pathlib import Path
from datetime import datetime
from googletrans import Translator

# Import functions from the original script
from spanish_sentence_miner import (
    test_anki_connection,
    parse_input_file,
    add_anki_card,
    append_to_processed_file,
    rewrite_input_file,
    INPUT_FILE,
    PROCESSED_FILE
)


class SentenceMinerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Spanish Sentence Miner")
        self.root.geometry("1100x850")

        # Initialize translator
        self.translator = Translator()

        # Session counter
        self.words_added_count = 0

        # Current selection
        self.selected_word = None
        self.sentence_counts = {}  # Track duplicate sentences
        self.is_manual_translation = False  # Track if translation was manually selected

        # Create GUI
        self.create_widgets()

        # Test Anki connection on startup
        self.root.after(100, self.test_connection)

    def create_widgets(self):
        """Create all GUI widgets."""

        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # Title
        title_label = ttk.Label(main_frame, text="Spanish Sentence Miner",
                               font=('Arial', 24, 'bold'))
        title_label.grid(row=0, column=0, pady=(0, 10))

        # Status bar
        self.status_label = ttk.Label(main_frame, text="Checking Anki connection...",
                                     foreground="gray", font=('Arial', 15))
        self.status_label.grid(row=1, column=0, pady=(0, 5))

        # Counter
        self.counter_label = ttk.Label(main_frame, text="Words added this session: 0",
                                      font=('Arial', 15, 'bold'))
        self.counter_label.grid(row=2, column=0, pady=(0, 10))

        # Instructions
        instructions = ttk.Label(main_frame,
                                text="Paste Spanish sentence below, then select target word(s) (double-click or click-and-drag):",
                                font=('Arial', 15))
        instructions.grid(row=3, column=0, sticky=tk.W, pady=(10, 5))

        # Spanish sentence input area
        sentence_frame = ttk.LabelFrame(main_frame, text="Spanish Sentence", padding="5")
        sentence_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=5)
        sentence_frame.columnconfigure(0, weight=1)
        sentence_frame.configure(relief='solid', borderwidth=2)

        self.sentence_text = tk.Text(sentence_frame, height=3, width=80, wrap=tk.WORD,
                                     font=('Arial', 16), bg='#E3F2FD')
        self.sentence_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.sentence_text.bind('<KeyRelease>', self.on_sentence_change)
        self.sentence_text.bind('<Double-Button-1>', self.on_word_double_click)
        self.sentence_text.bind('<ButtonRelease-1>', self.on_text_selection)
        self.sentence_text.bind('<<Paste>>', self.on_paste)

        # Selected target word display
        word_frame = ttk.LabelFrame(main_frame, text="Target Word/Phrase (Double-click or drag to select)",
                                   padding="5")
        word_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=5)
        word_frame.columnconfigure(0, weight=1)
        word_frame.configure(relief='solid', borderwidth=2)

        # Create a frame inside to apply background color
        word_inner_frame = tk.Frame(word_frame, bg='#FFF9C4')
        word_inner_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        word_inner_frame.columnconfigure(0, weight=1)

        self.target_word_label = tk.Label(word_inner_frame, text="(No word selected)",
                                          font=('Arial', 18, 'bold'),
                                          foreground="red", bg='#FFF9C4')
        self.target_word_label.grid(row=0, column=0, pady=5)

        # Translations display
        translation_frame = ttk.LabelFrame(main_frame, text="Translations", padding="5")
        translation_frame.grid(row=6, column=0, sticky=(tk.W, tk.E), pady=5)
        translation_frame.columnconfigure(0, weight=1)
        translation_frame.configure(relief='solid', borderwidth=2)

        # Sentence translation
        ttk.Label(translation_frame, text="Full Sentence (click word/phrase for back of card):", font=('Arial', 15, 'bold')).grid(row=0, column=0,
                                                                 sticky=tk.W)
        self.sentence_translation_text = scrolledtext.ScrolledText(
            translation_frame, height=2, width=80, wrap=tk.WORD,
            font=('Arial', 16), bg='#E8F5E9', cursor='hand2'
        )
        self.sentence_translation_text.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        self.sentence_translation_text.bind('<Button-1>', self.on_translation_click)

        # Word translation
        self.word_translation_label = ttk.Label(translation_frame, text="Target Word/Phrase (auto):", font=('Arial', 15, 'bold'))
        self.word_translation_label.grid(row=2, column=0, sticky=tk.W)
        self.word_translation_text = scrolledtext.ScrolledText(
            translation_frame, height=2, width=80, wrap=tk.WORD,
            font=('Arial', 16), state='disabled', bg='#E8F5E9'
        )
        self.word_translation_text.grid(row=3, column=0, sticky=(tk.W, tk.E))

        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=7, column=0, pady=20)

        # Configure button style for larger text
        style = ttk.Style()
        style.configure('Large.TButton', font=('Arial', 14))

        # Add to words list button
        self.add_button = ttk.Button(buttons_frame, text="Add to Words List",
                                    command=self.add_to_words_list,
                                    state='disabled', style='Large.TButton')
        self.add_button.grid(row=0, column=0, padx=5)

        # Clear form button
        clear_button = ttk.Button(buttons_frame, text="Clear Form",
                                 command=self.clear_form, style='Large.TButton')
        clear_button.grid(row=0, column=1, padx=5)

        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=8, column=0,
                                                            sticky=(tk.W, tk.E),
                                                            pady=20)

        # Batch processing section
        batch_frame = ttk.LabelFrame(main_frame, text="Batch Processing", padding="10")
        batch_frame.grid(row=9, column=0, sticky=(tk.W, tk.E))
        batch_frame.configure(relief='solid', borderwidth=2)

        # Create inner frame for background color
        batch_inner_frame = tk.Frame(batch_frame, bg='#F5F5F5')
        batch_inner_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        batch_frame.columnconfigure(0, weight=1)

        batch_label = tk.Label(batch_inner_frame,
                               text=f"Process all entries from {INPUT_FILE} and add to Anki:",
                               font=('Arial', 15), bg='#F5F5F5')
        batch_label.grid(row=0, column=0, sticky=tk.W, pady=(5, 10), padx=5)

        self.process_button = ttk.Button(batch_inner_frame, text="Process All → Anki",
                                        command=self.process_all_to_anki,
                                        state='disabled', style='Large.TButton')
        self.process_button.grid(row=1, column=0, pady=(0, 5), padx=5)

        # Configure row weights for proper expansion
        for i in range(10):
            main_frame.rowconfigure(i, weight=0)
        main_frame.rowconfigure(6, weight=1)  # Translation frame can expand

    def test_connection(self):
        """Test connection to Anki."""
        try:
            if test_anki_connection():
                self.status_label.config(text="✓ Connected to Anki", foreground="green")
                self.add_button.config(state='normal')
                self.process_button.config(state='normal')
            else:
                self.status_label.config(
                    text="✗ Anki connection failed - Check console for details",
                    foreground="red"
                )
                messagebox.showerror(
                    "Anki Connection Failed",
                    "Could not connect to Anki. Make sure:\n"
                    "1. Anki is running\n"
                    "2. AnkiConnect add-on is installed\n"
                    "3. The deck '2025 Spanish Immersion' exists"
                )
        except Exception as e:
            self.status_label.config(text=f"✗ Error: {str(e)}", foreground="red")
            messagebox.showerror("Connection Error", str(e))

    def on_paste(self, event=None):
        """Handle paste event - strip line breaks from pasted text."""
        try:
            # Get clipboard content
            clipboard_text = self.root.clipboard_get()

            # Strip line breaks and carriage returns
            cleaned_text = clipboard_text.replace('\n', ' ').replace('\r', ' ')

            # Remove multiple spaces
            cleaned_text = ' '.join(cleaned_text.split())

            # Insert cleaned text at cursor position
            self.sentence_text.insert(tk.INSERT, cleaned_text)

            # Prevent default paste behavior
            return "break"
        except Exception:
            # If clipboard is empty or error occurs, allow default behavior
            pass

    def on_sentence_change(self, event=None):
        """Handle sentence text changes - translate when pasted."""
        sentence = self.sentence_text.get("1.0", tk.END).strip()

        if sentence and len(sentence) > 3:  # Only translate if there's actual content
            # Debounce - only translate after a short delay
            if hasattr(self, '_translate_timer'):
                self.root.after_cancel(self._translate_timer)
            self._translate_timer = self.root.after(500, self.translate_sentence)

    def translate_sentence(self):
        """Translate the full Spanish sentence to English."""
        sentence = self.sentence_text.get("1.0", tk.END).strip()

        if not sentence:
            return

        try:
            # Translate from Spanish to English
            translation = self.translator.translate(sentence, src='es', dest='en')

            # Update the sentence translation display
            self.sentence_translation_text.delete("1.0", tk.END)
            self.sentence_translation_text.insert("1.0", translation.text)

        except Exception as e:
            self.sentence_translation_text.delete("1.0", tk.END)
            self.sentence_translation_text.insert("1.0", f"Translation error: {str(e)}")

    def on_word_double_click(self, event):
        """Handle double-click on a word to select it as target."""
        # Get the clicked position
        index = self.sentence_text.index(f"@{event.x},{event.y}")

        # Get the full text
        text = self.sentence_text.get("1.0", tk.END)

        # Find word boundaries
        # Get character position
        line, char = map(int, index.split('.'))

        # Calculate absolute position in text
        lines = text.split('\n')
        abs_pos = sum(len(lines[i]) + 1 for i in range(line - 1)) + char

        # Find word boundaries (letters, numbers, and common Spanish characters)
        word_chars = re.compile(r'[a-záéíóúñüA-ZÁÉÍÓÚÑÜ]')

        # Find start of word
        start = abs_pos
        while start > 0 and word_chars.match(text[start - 1]):
            start -= 1

        # Find end of word
        end = abs_pos
        while end < len(text) and word_chars.match(text[end]):
            end += 1

        # Extract the word
        word = text[start:end].strip()

        if word:
            self.selected_word = word
            self.target_word_label.config(text=word)

            # Clear previous highlighting
            self.sentence_text.tag_remove("highlight", "1.0", tk.END)

            # Highlight all occurrences of the word
            self.highlight_word_occurrences(word)

            # Translate the selected word
            self.translate_word(word)

    def on_text_selection(self, event):
        """Handle text selection (click-and-drag) for multi-word phrases."""
        try:
            # Get the selected text
            selected = self.sentence_text.get(tk.SEL_FIRST, tk.SEL_LAST).strip()

            if selected and len(selected) > 0:
                self.selected_word = selected
                self.target_word_label.config(text=selected)

                # Clear previous highlighting
                self.sentence_text.tag_remove("highlight", "1.0", tk.END)

                # Highlight the selection
                self.highlight_word_occurrences(selected)

                # Translate the selected phrase
                self.translate_word(selected)
                self.is_manual_translation = False  # Reset to auto when new selection made
                self.word_translation_label.config(text="Target Word/Phrase (auto):")
        except tk.TclError:
            # No selection made, ignore
            pass

    def highlight_word_occurrences(self, word):
        """Highlight all occurrences of the word in the sentence."""
        text = self.sentence_text.get("1.0", tk.END)

        # Configure tag for highlighting
        self.sentence_text.tag_config("highlight", background="yellow", foreground="red")

        # Find and highlight all occurrences (case-insensitive)
        pattern = re.compile(re.escape(word), re.IGNORECASE)

        for match in pattern.finditer(text):
            start_pos = match.start()
            end_pos = match.end()

            # Convert to tkinter index format
            lines_before = text[:start_pos].count('\n')
            chars_in_line = start_pos - text[:start_pos].rfind('\n') - 1

            start_index = f"{lines_before + 1}.{chars_in_line}"
            end_index = f"{lines_before + 1}.{chars_in_line + len(match.group())}"

            self.sentence_text.tag_add("highlight", start_index, end_index)

    def translate_word(self, word):
        """Translate the selected target word to English."""
        try:
            # Translate from Spanish to English
            translation = self.translator.translate(word, src='es', dest='en')

            # Update the word translation display
            self.word_translation_text.config(state='normal')
            self.word_translation_text.delete("1.0", tk.END)
            self.word_translation_text.insert("1.0", translation.text)
            self.word_translation_text.config(state='disabled')

        except Exception as e:
            self.word_translation_text.config(state='normal')
            self.word_translation_text.delete("1.0", tk.END)
            self.word_translation_text.insert("1.0", f"Translation error: {str(e)}")
            self.word_translation_text.config(state='disabled')

    def on_translation_click(self, event):
        """Handle clicking on a word/phrase in the sentence translation to select it for the back of the card."""
        # Get the clicked position
        index = self.sentence_translation_text.index(f"@{event.x},{event.y}")

        # Get the full text
        text = self.sentence_translation_text.get("1.0", tk.END)

        # Find word boundaries
        line, char = map(int, index.split('.'))

        # Calculate absolute position in text
        lines = text.split('\n')
        abs_pos = sum(len(lines[i]) + 1 for i in range(line - 1)) + char

        # Find word boundaries (letters, numbers, apostrophes)
        word_chars = re.compile(r'[a-zA-Z0-9\']')

        # Find start of word
        start = abs_pos
        while start > 0 and word_chars.match(text[start - 1]):
            start -= 1

        # Find end of word
        end = abs_pos
        while end < len(text) and word_chars.match(text[end]):
            end += 1

        # Extract the clicked word/phrase
        clicked_word = text[start:end].strip()

        if clicked_word:
            # Update the word translation display with the clicked text
            self.word_translation_text.config(state='normal')
            self.word_translation_text.delete("1.0", tk.END)
            self.word_translation_text.insert("1.0", clicked_word)
            self.word_translation_text.config(state='disabled')

            # Mark as manually selected
            self.is_manual_translation = True
            self.word_translation_label.config(text="Target Word/Phrase (manual):")

            # Add highlighting to show what was selected
            self.sentence_translation_text.tag_remove("trans_highlight", "1.0", tk.END)
            self.sentence_translation_text.tag_config("trans_highlight", background="#FFEB3B", foreground="blue")

            # Highlight the clicked word in the translation
            pattern = re.compile(re.escape(clicked_word), re.IGNORECASE)
            for match in pattern.finditer(text):
                start_pos = match.start()
                end_pos = match.end()

                # Convert to tkinter index format
                lines_before = text[:start_pos].count('\n')
                chars_in_line = start_pos - text[:start_pos].rfind('\n') - 1

                start_index = f"{lines_before + 1}.{chars_in_line}"
                end_index = f"{lines_before + 1}.{chars_in_line + len(match.group())}"

                self.sentence_translation_text.tag_add("trans_highlight", start_index, end_index)

    def add_to_words_list(self):
        """Add the current entry to words_to_process.txt."""
        # Get values
        sentence = self.sentence_text.get("1.0", tk.END).strip()
        target_word = self.selected_word
        word_translation = self.word_translation_text.get("1.0", tk.END).strip()

        # Validate
        if not sentence:
            messagebox.showwarning("Missing Data", "Please enter a Spanish sentence.")
            return

        if not target_word:
            messagebox.showwarning("Missing Data", "Please select a target word by double-clicking it.")
            return

        if not word_translation or word_translation.startswith("Translation error"):
            messagebox.showwarning("Missing Data", "Please wait for word translation to complete.")
            return

        # Append to file
        try:
            # Check if file exists and has content
            file_path = Path(INPUT_FILE)
            needs_newline = False

            if file_path.exists():
                with open(INPUT_FILE, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Add newline if file doesn't end with one
                    if content and not content.endswith('\n'):
                        needs_newline = True

            # Append the new entry
            with open(INPUT_FILE, 'a', encoding='utf-8') as f:
                if needs_newline:
                    f.write('\n')
                # Add blank line before new entry if file already has content
                if file_path.exists() and file_path.stat().st_size > 0:
                    f.write('\n')

                f.write(f"{sentence}\n")
                f.write(f"{target_word}\n")
                f.write(f"{word_translation}\n")

            # Increment counter
            self.words_added_count += 1
            self.counter_label.config(text=f"Words added this session: {self.words_added_count}")

            # Show success message
            messagebox.showinfo("Success",
                              f"Added to {INPUT_FILE}:\n\n"
                              f"Sentence: {sentence}\n"
                              f"Word: {target_word}\n"
                              f"Translation: {word_translation}")

            # Clear the form
            self.clear_form()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to add to file: {str(e)}")

    def clear_form(self):
        """Clear all input fields."""
        self.sentence_text.delete("1.0", tk.END)
        self.sentence_text.tag_remove("highlight", "1.0", tk.END)
        self.selected_word = None
        self.target_word_label.config(text="(No word selected)")

        self.sentence_translation_text.delete("1.0", tk.END)
        self.sentence_translation_text.tag_remove("trans_highlight", "1.0", tk.END)

        self.word_translation_text.config(state='normal')
        self.word_translation_text.delete("1.0", tk.END)
        self.word_translation_text.config(state='disabled')

        # Reset translation state
        self.is_manual_translation = False
        self.word_translation_label.config(text="Target Word/Phrase (auto):")

    def process_all_to_anki(self):
        """Process all entries from words_to_process.txt and add to Anki."""
        # Check if file exists
        if not Path(INPUT_FILE).exists():
            messagebox.showinfo("No File", f"{INPUT_FILE} does not exist or is empty.")
            return

        try:
            # Parse entries
            entries = parse_input_file(INPUT_FILE)

            if not entries:
                messagebox.showinfo("No Entries", f"No valid entries found in {INPUT_FILE}")
                return

            # Confirm with user
            response = messagebox.askyesno(
                "Confirm Processing",
                f"Found {len(entries)} entries to process.\n\n"
                f"This will add them to Anki and remove successful entries from {INPUT_FILE}.\n\n"
                "Continue?"
            )

            if not response:
                return

            # Process entries
            successful_entries = []
            failed_entries = []

            for idx, entry in enumerate(entries, 1):
                try:
                    # Check for duplicate sentences and append suffix if needed
                    sentence = entry['sentence']
                    if sentence in self.sentence_counts:
                        self.sentence_counts[sentence] += 1
                        sentence_with_suffix = f"{sentence} ({self.sentence_counts[sentence]})"
                    else:
                        self.sentence_counts[sentence] = 1
                        sentence_with_suffix = sentence

                    note_id = add_anki_card(
                        sentence_with_suffix,
                        entry['word'],
                        entry['translation']
                    )

                    successful_entries.append(entry)
                    print(f"[{idx}/{len(entries)}] ✓ Added: {entry['word']} (Note ID: {note_id})")

                except Exception as e:
                    failed_entries.append(entry)
                    print(f"[{idx}/{len(entries)}] ✗ Failed: {entry['word']} - {e}")

            # Update processed file
            if successful_entries:
                append_to_processed_file(successful_entries)

            # Remove successful entries from input file
            rewrite_input_file(failed_entries)

            # Show results
            messagebox.showinfo(
                "Processing Complete",
                f"Successfully added: {len(successful_entries)} cards\n"
                f"Failed: {len(failed_entries)} cards\n\n"
                f"Processed entries logged to {PROCESSED_FILE}"
            )

        except Exception as e:
            messagebox.showerror("Error", f"Processing failed: {str(e)}")


def main():
    """Main function to run the GUI."""
    root = tk.Tk()
    app = SentenceMinerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
