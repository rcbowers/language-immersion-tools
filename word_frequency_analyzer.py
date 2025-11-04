#!/usr/bin/env python3
"""
Document Word Frequency Analyzer

Analyzes various document types (.srt, .pdf, .txt) to calculate unique word counts and generate frequency histograms.
Designed for Spanish language text with proper handling of accents and special characters.
"""

import os
import re
import argparse
from collections import Counter
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for compatibility

# PDF parsing imports - will be imported conditionally
try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


# Common Spanish stopwords to filter out
SPANISH_STOPWORDS = {'es', 'tulio', 'el','oh','te','una','un','uno','ah','vamos','voy','esta','esto','este',
    'el', 'la', 'de', 'que', 'y', 'a', 'en', 'un', 'ser', 'se', 'no', 'haber',
    'por', 'con', 'su', 'para', 'como', 'estar', 'tener', 'le', 'lo', 'todo',
    'pero', 'más', 'hacer', 'o', 'poder', 'decir', 'este', 'ir', 'otro', 'ese',
    'la', 'si', 'me', 'ya', 'ver', 'porque', 'dar', 'cuando', 'él', 'muy',
    'sin', 'vez', 'mucho', 'saber', 'qué', 'sobre', 'mi', 'alguno', 'mismo',
    'yo', 'también', 'hasta', 'año', 'dos', 'querer', 'entre', 'así',
    'desde', 'grande', 'eso', 'ni', 'nos', 'ella',
    'sí', 'día', 'uno', 'bien', 'poco', 'deber', 'entonces',
    'nuestro', 'tan', 'donde', 'ahora', 'parte',
    'acabar', 'millón', 'ante', 'las', 'los', 'del', 'al'
}


def is_srt_metadata_line(line):
    """Check if a line is SRT metadata (sequence number or timestamp)."""
    line = line.strip()
    # Check if line is a number (sequence number)
    if line.isdigit():
        return True
    # Check if line contains timestamp (HH:MM:SS,mmm --> HH:MM:SS,mmm)
    if '-->' in line:
        return True
    # Check if line is empty
    if not line:
        return True
    return False


def clean_spanish_text(text):
    """
    Clean Spanish text by removing punctuation while preserving Spanish characters.

    Args:
        text: Raw text string

    Returns:
        Cleaned lowercase text
    """
    # Convert to lowercase
    text = text.lower()

    # Remove punctuation but keep Spanish letters and spaces
    # Spanish alphabet includes: a-z, á, é, í, ó, ú, ñ, ü
    text = re.sub(r'[^a-záéíóúñü\s]', ' ', text)

    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def parse_srt_file(filepath):
    """
    Parse an SRT file and extract all words.

    Args:
        filepath: Path to the .srt file

    Returns:
        List of cleaned words
    """
    words = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                # Skip metadata lines
                if is_srt_metadata_line(line):
                    continue

                # Clean and extract words from subtitle text
                cleaned = clean_spanish_text(line)
                if cleaned:
                    words.extend(cleaned.split())

    except Exception as e:
        print(f"Warning: Error reading {filepath}: {e}")

    return words


def parse_pdf_file(filepath):
    """
    Parse a PDF file and extract all words.

    Args:
        filepath: Path to the .pdf file

    Returns:
        List of cleaned words
    """
    if not PDF_AVAILABLE:
        raise ImportError("PyPDF2 is required to read PDF files. Install it with: pip install PyPDF2")

    words = []

    try:
        with open(filepath, 'rb') as f:
            pdf_reader = PdfReader(f)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()

                # Clean and extract words from text
                cleaned = clean_spanish_text(text)
                if cleaned:
                    words.extend(cleaned.split())

    except Exception as e:
        print(f"Warning: Error reading {filepath}: {e}")

    return words


def parse_txt_file(filepath):
    """
    Parse a plain text file and extract all words.

    Args:
        filepath: Path to the .txt file

    Returns:
        List of cleaned words
    """
    words = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                # Clean and extract words from text
                cleaned = clean_spanish_text(line)
                if cleaned:
                    words.extend(cleaned.split())

    except Exception as e:
        print(f"Warning: Error reading {filepath}: {e}")

    return words


def parse_document(filepath):
    """
    Parse a document file based on its extension.

    Args:
        filepath: Path to the document file

    Returns:
        List of cleaned words
    """
    file_path = Path(filepath)
    extension = file_path.suffix.lower()

    if extension == '.srt':
        return parse_srt_file(filepath)
    elif extension == '.pdf':
        return parse_pdf_file(filepath)
    elif extension == '.txt':
        return parse_txt_file(filepath)
    else:
        print(f"Warning: Unsupported file type '{extension}' for {filepath}")
        return []


def filter_stopwords(words, remove_stopwords=True):
    """
    Filter out common Spanish stopwords.

    Args:
        words: List of words
        remove_stopwords: Whether to remove stopwords

    Returns:
        Tuple of (filtered_words, stopwords_count)
    """
    if not remove_stopwords:
        return words, 0

    original_count = len(words)
    filtered_words = [word for word in words if word not in SPANISH_STOPWORDS]
    stopwords_count = original_count - len(filtered_words)

    return filtered_words, stopwords_count


def analyze_documents(path, file_types=None, remove_stopwords=True):
    """
    Analyze document files in a folder or analyze a single file.

    Args:
        path: Path to folder containing documents or path to a single document file
        file_types: List of file extensions to include (e.g., ['.srt', '.pdf', '.txt']).
                   If None, includes all supported types.
        remove_stopwords: Whether to remove common Spanish stopwords

    Returns:
        Tuple of (word_freq, stopwords_filtered, total_words_after_filtering, unique_words)
    """
    path_obj = Path(path)

    if not path_obj.exists():
        raise ValueError(f"Path does not exist: {path}")

    # Default to all supported types if not specified
    if file_types is None:
        file_types = ['.srt', '.pdf', '.txt']

    # Normalize extensions to lowercase
    file_types = [ext.lower() if ext.startswith('.') else f'.{ext.lower()}' for ext in file_types]

    # Handle single file vs folder
    if path_obj.is_file():
        if path_obj.suffix.lower() not in file_types:
            raise ValueError(f"File type '{path_obj.suffix}' is not in specified file types: {file_types}")
        document_files = [path_obj]
    else:
        # Find all matching files
        document_files = []
        for ext in file_types:
            document_files.extend(path_obj.glob(f"*{ext}"))

        if not document_files:
            raise ValueError(f"No files with extensions {file_types} found in: {path}")

    print(f"Found {len(document_files)} file(s) to process")

    all_words = []

    # Process each file
    for doc_file in document_files:
        print(f"Processing: {doc_file.name}")
        words = parse_document(doc_file)
        all_words.extend(words)

    # Filter stopwords if requested
    stopwords_filtered = 0
    if remove_stopwords:
        print(f"Filtering out common Spanish stopwords...")
        all_words, stopwords_filtered = filter_stopwords(all_words, remove_stopwords)
    else:
        all_words, stopwords_filtered = filter_stopwords(all_words, False)

    # Count word frequencies
    word_freq = Counter(all_words)
    total_words = sum(word_freq.values())
    unique_words = len(word_freq)

    return word_freq, stopwords_filtered, total_words, unique_words


def create_histogram(word_freq, output_path, source_filename, total_words, unique_words, stopwords_filtered):
    """
    Create and save a comprehensive histogram visualization with 3 subplots showing word frequencies.

    Args:
        word_freq: Counter object with word frequencies
        output_path: Path to save the histogram image
        source_filename: Name of the source file being analyzed
        total_words: Total word count after filtering
        unique_words: Number of unique words
        stopwords_filtered: Number of common words filtered out
    """
    if not word_freq:
        print("No words to plot!")
        return

    # Create figure with 3 vertically stacked subplots
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(40, 24))

    # Add overall title with statistics
    stats_text = f"Word Frequency Analysis\n"
    stats_text += f"Source: {source_filename}\n"
    stats_text += f"Total words: {total_words:,} | Unique words: {unique_words:,} | Common words filtered: {stopwords_filtered:,}"
    fig.suptitle(stats_text, fontsize=16, fontweight='bold', y=0.995)

    # Subplot 1: Top 200 words
    top_200 = word_freq.most_common(200)
    if top_200:
        words_200, freq_200 = zip(*top_200)
        ax1.bar(range(len(words_200)), freq_200, color='steelblue', edgecolor='black')
        ax1.set_xlabel('Words', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Frequency', fontsize=12, fontweight='bold')
        ax1.set_title(f'Top 200 Most Frequent Words', fontsize=14, fontweight='bold')
        ax1.set_xticks(range(len(words_200)))
        ax1.set_xticklabels(words_200, rotation=45, ha='right', fontsize=4)
        ax1.grid(axis='y', alpha=0.3)

    # Subplot 2: Top 1000 words
    top_1000 = word_freq.most_common(1000)
    if top_1000:
        words_1000, freq_1000 = zip(*top_1000)
        ax2.bar(range(len(words_1000)), freq_1000, color='steelblue', edgecolor='black')
        ax2.set_xlabel('Words', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Frequency', fontsize=12, fontweight='bold')
        ax2.set_title(f'Top 1000 Most Frequent Words', fontsize=14, fontweight='bold')
        ax2.set_xticks(range(len(words_1000)))
        ax2.set_xticklabels(words_1000, rotation=45, ha='right', fontsize=2)
        ax2.grid(axis='y', alpha=0.3)

    # Subplot 3: All words
    all_words_data = word_freq.most_common()
    if all_words_data:
        words_all, freq_all = zip(*all_words_data)
        ax3.bar(range(len(words_all)), freq_all, color='steelblue', edgecolor='black')
        ax3.set_xlabel('Words', fontsize=12, fontweight='bold')
        ax3.set_ylabel('Frequency', fontsize=12, fontweight='bold')
        ax3.set_title(f'All {len(words_all)} Unique Words', fontsize=14, fontweight='bold')
        ax3.set_xticks(range(len(words_all)))
        ax3.set_xticklabels(words_all, rotation=45, ha='right', fontsize=2)
        ax3.grid(axis='y', alpha=0.3)

    # Adjust layout to prevent overlap
    plt.tight_layout(rect=[0, 0, 1, 0.99])

    # Save figure
    plt.savefig(output_path, dpi=700, bbox_inches='tight')
    print(f"\nHistogram saved to: {output_path}")
    plt.close()


def print_statistics(word_freq, top_n=2000):
    """
    Print word frequency statistics to console.

    Args:
        word_freq: Counter object with word frequencies
        top_n: Number of top words to display
    """
    total_words = sum(word_freq.values())
    unique_words = len(word_freq)

    print("\n" + "="*60)
    print("WORD FREQUENCY ANALYSIS RESULTS")
    print("="*60)
    print(f"Total words (after filtering): {total_words:,}")
    print(f"Unique words: {unique_words:,}")
    print("="*60)

    print(f"\nTop {top_n} Most Frequent Words:")
    print("-"*60)
    print(f"{'Rank':<6} {'Word':<25} {'Frequency':<15} {'Percentage':<10}")
    print("-"*60)

    for rank, (word, count) in enumerate(word_freq.most_common(top_n), 1):
        percentage = (count / total_words) * 100
        print(f"{rank:<6} {word:<25} {count:<15,} {percentage:<10.2f}%")

    print("="*60)


def save_full_word_list(word_freq, output_path):
    """
    Save complete word frequency list to a text file.

    Args:
        word_freq: Counter object with word frequencies
        output_path: Path to save the text file
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("COMPLETE WORD FREQUENCY LIST\n")
        f.write("="*60 + "\n\n")
        f.write(f"Total unique words: {len(word_freq):,}\n")
        f.write(f"Total word count: {sum(word_freq.values()):,}\n\n")
        f.write("-"*60 + "\n")
        f.write(f"{'Word':<30} {'Frequency':<15}\n")
        f.write("-"*60 + "\n")

        for word, count in word_freq.most_common():
            f.write(f"{word:<30} {count:<15,}\n")

    print(f"Complete word list saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze document files (SRT, PDF, TXT) for word frequency and generate histograms',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ./subtitles                              # Analyze all supported files in folder
  %(prog)s document.pdf                              # Analyze a single PDF file
  %(prog)s ./documents --types srt pdf               # Only analyze .srt and .pdf files
  %(prog)s ./subtitles --top 100                     # Show top 100 words
  %(prog)s ./subtitles --keep-stopwords              # Keep common stopwords
  %(prog)s ./subtitles --output word_analysis.png    # Custom output filename
        """
    )

    parser.add_argument(
        'path',
        help='Path to folder containing documents or path to a single document file'
    )

    parser.add_argument(
        '--types',
        nargs='+',
        default=None,
        help='File types to analyze (e.g., srt pdf txt). Default: all supported types'
    )

    parser.add_argument(
        '--top', '-t',
        type=int,
        default=50,
        help='Number of top words to display (default: 50)'
    )

    parser.add_argument(
        '--output', '-o',
        default='word_frequency_histogram.png',
        help='Output filename for histogram chart (default: word_frequency_histogram.png)'
    )

    parser.add_argument(
        '--keep-stopwords',
        action='store_true',
        help='Keep common Spanish stopwords (el, la, de, etc.)'
    )

    parser.add_argument(
        '--save-full-list',
        action='store_true',
        help='Save complete word frequency list to text file'
    )

    args = parser.parse_args()

    try:
        # Analyze the path
        path_type = "file" if Path(args.path).is_file() else "folder"
        print(f"\nAnalyzing documents in {path_type}: {args.path}\n")

        word_freq, stopwords_filtered, total_words, unique_words = analyze_documents(
            args.path,
            file_types=args.types,
            remove_stopwords=not args.keep_stopwords
        )

        # Extract source filename for output naming
        source_path = Path(args.path)
        if source_path.is_file():
            source_filename = source_path.stem
        else:
            source_filename = source_path.name

        # Generate output filename: {source}_word_analysis.png
        output_path = f"./outputs/{source_filename}_word_analysis.png"

        # Print statistics to console
        print_statistics(word_freq, args.top)

        # Create and save histogram with comprehensive information
        create_histogram(word_freq, output_path, source_filename, total_words, unique_words, stopwords_filtered)

        # Optionally save full word list
        if args.save_full_list:
            full_list_path = f"./outputs/{source_filename}_full_list.txt"
            save_full_word_list(word_freq, full_list_path)

        print("\nAnalysis complete!")

    except Exception as e:
        print(f"\nError: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
