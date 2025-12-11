#!/usr/bin/env python3
"""
Spanish Sentence Mining GUI Tool
A tkinter-based GUI for creating Spanish Anki flashcards with automatic translation.
Now includes automatic Anki startup and connection monitoring.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import re
import subprocess
import time
import os
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

# ============================================================================
# CONFIGURATION - Update this path to your Anki executable
# ============================================================================
ANKI_PATH = r"C:\Program Files\Anki\anki.exe"  # Update this path!


# ============================================================================


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

        # Anki process reference
        self.anki_process = None

        # Create GUI
        self.create_widgets()

        # Start Anki and test connection
        self.root.after(20, self.startup_sequence)

    def startup_sequence(self):
        """Start Anki and wait for connection to be established."""
        self.status_label.config(text="Starting Anki...", foreground="orange")
        self.root.update()

        # Check if Anki is already running
        if self.check_anki_running():
            self.status_label.config(text="Anki already running, testing connection...",
                                     foreground="orange")
            self.root.update()
            time.sleep(1)  # Brief delay
            self.test_connection()
            return

        # Start Anki if not running
        if not self.start_anki():
            return  # Error already shown

        # Wait for Anki to start and establish connection
        self.wait_for_connection()

    def start_anki(self):
        """Start the Anki application."""
        try:
            # Check if path exists
            if not os.path.exists(ANKI_PATH):
                messagebox.showerror(
                    "Anki Not Found",
                    f"Anki executable not found at:\n{ANKI_PATH}\n\n"
                    "Please update the ANKI_PATH variable at the top of the script."
                )
                self.status_label.config(text="❌ Anki path not found", foreground="red")
                return False

            # Start Anki process
            self.anki_process = subprocess.Popen(
                [ANKI_PATH],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            self.status_label.config(text="Anki started, waiting for connection...",
                                     foreground="orange")
            return True

        except Exception as e:
            messagebox.showerror("Error Starting Anki",
                                 f"Failed to start Anki:\n{str(e)}")
            self.status_label.config(text="❌ Failed to start Anki", foreground="red")
            return False

    def check_anki_running(self):
        """Check if Anki is already running."""
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                if 'anki' in proc.info['name'].lower():
                    return True
        except ImportError:
            # If psutil not available, just try to connect
            pass
        return False

    def wait_for_connection(self, max_attempts=30, delay=1):
        """Wait for Anki connection to be established."""
        attempt = 0

        def check_connection():
            nonlocal attempt
            attempt += 1

            if test_anki_connection():
                self.on_connection_success()
            elif attempt >= max_attempts:
                self.on_connection_timeout()
            else:
                # Update status with countdown
                remaining = max_attempts - attempt
                self.status_label.config(
                    text=f"Waiting for Anki connection... ({remaining}s remaining)",
                    foreground="orange"
                )
                # Try again after delay
                self.root.after(delay * 1000, check_connection)

        # Start checking
        check_connection()

    def on_connection_success(self):
        """Called when Anki connection is successfully established."""
        self.status_label.config(text="✓ Connected to Anki", foreground="green")
        self.process_button.config(state='normal')

    def on_connection_timeout(self):
        """Called when connection attempts time out."""
        messagebox.showwarning(
            "Connection Timeout",
            "Could not establish connection to Anki.\n\n"
            "Please make sure:\n"
            "1. Anki is running\n"
            "2. AnkiConnect add-on is installed\n"
            "3. AnkiConnect is enabled in Anki's Tools > Add-ons menu\n\n"
            "You can try restarting this application."
        )
        self.status_label.config(text="❌ Connection to Anki failed", foreground="red")

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
        self.status_label = ttk.Label(main_frame, text="Initializing...",
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
        ttk.Label(translation_frame, text="Full Sentence (click word/phrase for back of card):",
                  font=('Arial', 15, 'bold')).grid(row=0, column=0,
                                                   sticky=tk.W)
        self.sentence_translation_text = scrolledtext.ScrolledText(
            translation_frame, height=2, width=80, wrap=tk.WORD,
            font=('Arial', 16), bg='#E8F5E9', cursor='hand2'
        )
        self.sentence_translation_text.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        self.sentence_translation_text.bind('<Button-1>', self.on_translation_click)

        # Word translation
        self.word_translation_label = ttk.Label(translation_frame, text="Target Word/Phrase (auto):",
                                                font=('Arial', 15, 'bold'))
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
        if test_anki_connection():
            self.on_connection_success()
        else:
            self.status_label.config(text="⚠ Not connected to Anki - Check AnkiConnect is running",
                                     foreground="red")

    def on_sentence_change(self, event=None):
        """Handle changes to sentence text."""
        # Clear highlights when text changes
        self.sentence_text.tag_remove("highlight", "1.0", tk.END)

    def on_paste(self, event=None):
        """Handle paste event with auto-translate."""
        # Schedule translation after paste completes
        self.root.after(100, self.auto_translate_sentence)

    def on_word_double_click(self, event):
        """Handle double-click on a word to select it."""
        # Get the clicked word
        index = self.sentence_text.index(f"@{event.x},{event.y}")
        line_start = self.sentence_text.index(f"{index} linestart")
        line_end = self.sentence_text.index(f"{index} lineend")
        line = self.sentence_text.get(line_start, line_end)

        # Find word boundaries
        click_pos = int(index.split('.')[1])
        start = click_pos
        end = click_pos

        # Move start backward to word boundary
        while start > 0 and line[start - 1].isalnum():
            start -= 1

        # Move end forward to word boundary
        while end < len(line) and line[end].isalnum():
            end += 1

        word = line[start:end].strip()

        if word:
            self.select_word(word, f"{index.split('.')[0]}.{start}",
                             f"{index.split('.')[0]}.{end}")

    def on_text_selection(self, event=None):
        """Handle text selection (click and drag)."""
        try:
            selected_text = self.sentence_text.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
            if selected_text:
                self.select_word(selected_text, tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            # No selection
            pass

    def select_word(self, word, start_index, end_index):
        """Select and highlight a word."""
        self.selected_word = word
        self.target_word_label.config(text=word, foreground="darkblue")

        # Highlight in text widget
        self.sentence_text.tag_remove("highlight", "1.0", tk.END)
        self.sentence_text.tag_add("highlight", start_index, end_index)
        self.sentence_text.tag_config("highlight", background="yellow", foreground="darkblue")

        # Translate the word
        self.translate_word(word)

        # Enable add button
        self.add_button.config(state='normal')

    def auto_translate_sentence(self):
        """Automatically translate the sentence when pasted."""
        sentence = self.sentence_text.get("1.0", tk.END).strip()
        if sentence:
            self.translate_sentence(sentence)

    def translate_sentence(self, sentence):
        """Translate Spanish sentence to English."""
        try:
            translation = self.translator.translate(sentence, src='es', dest='en')
            self.sentence_translation_text.delete("1.0", tk.END)
            self.sentence_translation_text.insert("1.0", translation.text)
        except Exception as e:
            self.sentence_translation_text.delete("1.0", tk.END)
            self.sentence_translation_text.insert("1.0", f"Translation error: {str(e)}")

    def translate_word(self, word):
        """Translate selected word to English."""
        # Don't auto-translate if user manually selected a translation
        if self.is_manual_translation:
            return

        try:
            translation = self.translator.translate(word, src='es', dest='en')
            self.word_translation_text.config(state='normal')
            self.word_translation_text.delete("1.0", tk.END)
            self.word_translation_text.insert("1.0", translation.text)
            self.word_translation_text.config(state='disabled')
            self.word_translation_label.config(text="Target Word/Phrase (auto):")
        except Exception as e:
            self.word_translation_text.config(state='normal')
            self.word_translation_text.delete("1.0", tk.END)
            self.word_translation_text.insert("1.0", f"Translation error: {str(e)}")
            self.word_translation_text.config(state='disabled')

    def on_translation_click(self, event):
        """Handle click on sentence translation to select word for back of card."""
        # Get the index of the click
        index = self.sentence_translation_text.index(f"@{event.x},{event.y}")

        # Get the entire text
        text = self.sentence_translation_text.get("1.0", tk.END)

        # Find the word at the clicked position
        click_pos = self.sentence_translation_text.index(index)
        line_num, char_pos = map(int, click_pos.split('.'))

        # Get the line
        line_start = f"{line_num}.0"
        line_end = f"{line_num}.end"
        line = self.sentence_translation_text.get(line_start, line_end)

        # Find word boundaries
        start = char_pos
        end = char_pos

        # Move start backward to word boundary
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] in "-'"):
            start -= 1

        # Move end forward to word boundary
        while end < len(line) and (line[end].isalnum() or line[end] in "-'"):
            end += 1

        clicked_word = line[start:end].strip()

        if clicked_word:
            # Update the word translation field
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