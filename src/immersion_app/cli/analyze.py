"""Word-frequency analysis for subtitle, PDF, and text corpora."""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False


SPANISH_STOPWORDS = {
    "es", "el", "la", "de", "que", "y", "a", "en", "un", "ser", "se", "no", "haber", "por", "con", "su",
    "para", "como", "estar", "tener", "le", "lo", "todo", "pero", "más", "hacer", "o", "este", "ir", "otro",
    "ese", "algo", "tanto", "mientras", "hacia", "si", "me", "ya", "ver", "porque", "dar", "cuando", "él", "muy",
    "sin", "vez", "mucho", "saber", "qué", "sobre", "mi", "alguno", "mismo", "yo", "también", "hasta", "año",
    "dos", "querer", "entre", "así", "desde", "grande", "eso", "ni", "nos", "ella", "sí", "día", "bien", "poco",
    "deber", "entonces", "nuestro", "tan", "donde", "ahora", "parte", "las", "los", "del", "al",
}


def is_srt_metadata_line(line):
    line = line.strip()
    return not line or line.isdigit() or "-->" in line


def clean_spanish_text(text):
    text = text.lower()
    text = re.sub(r"[^a-záéíóúñü\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_accents(text):
    nfd = unicodedata.normalize("NFD", text)
    return "".join(char for char in nfd if unicodedata.category(char) != "Mn")


def lemmatize_spanish_text(text, nlp):
    doc = nlp(text)
    lemmas = []
    for token in doc:
        if token.is_alpha:
            lemmas.append(normalize_accents(token.lemma_.lower()))
    return lemmas


def parse_srt_file(filepath):
    words = []
    with open(filepath, "r", encoding="utf-8") as handle:
        for line in handle:
            if is_srt_metadata_line(line):
                continue
            cleaned = clean_spanish_text(line)
            if cleaned:
                words.extend(cleaned.split())
    return words


def parse_pdf_file(filepath):
    if not PDF_AVAILABLE:
        raise ImportError("pypdf is required to read PDF files.")
    words = []
    with open(filepath, "rb") as handle:
        pdf_reader = PdfReader(handle)
        for page in pdf_reader.pages:
            cleaned = clean_spanish_text(page.extract_text() or "")
            if cleaned:
                words.extend(cleaned.split())
    return words


def parse_txt_file(filepath):
    words = []
    with open(filepath, "r", encoding="utf-8") as handle:
        for line in handle:
            cleaned = clean_spanish_text(line)
            if cleaned:
                words.extend(cleaned.split())
    return words


def parse_document(filepath):
    extension = Path(filepath).suffix.lower()
    if extension == ".srt":
        return parse_srt_file(filepath)
    if extension == ".pdf":
        return parse_pdf_file(filepath)
    if extension == ".txt":
        return parse_txt_file(filepath)
    return []


def filter_stopwords(words, remove_stopwords=True):
    if not remove_stopwords:
        return words, 0
    filtered_words = [word for word in words if word not in SPANISH_STOPWORDS]
    return filtered_words, len(words) - len(filtered_words)


def analyze_documents(path, file_types=None, remove_stopwords=True, nlp=None):
    path_obj = Path(path)
    if not path_obj.exists():
        raise ValueError(f"Path does not exist: {path}")
    if file_types is None:
        file_types = [".srt", ".pdf", ".txt"]
    file_types = [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in file_types]

    if path_obj.is_file():
        if path_obj.suffix.lower() not in file_types:
            raise ValueError(f"File type '{path_obj.suffix}' is not in specified file types: {file_types}")
        document_files = [path_obj]
    else:
        document_files = []
        for ext in file_types:
            document_files.extend(path_obj.glob(f"*{ext}"))
        if not document_files:
            raise ValueError(f"No files with extensions {file_types} found in: {path}")

    all_words = []
    for doc_file in document_files:
        print(f"Processing: {doc_file.name}")
        all_words.extend(parse_document(doc_file))
    if nlp is not None:
        print("Applying lemmatization to group conjugations...")
        all_words = lemmatize_spanish_text(" ".join(all_words), nlp)
    all_words, stopwords_filtered = filter_stopwords(all_words, remove_stopwords)
    word_freq = Counter(all_words)
    return word_freq, stopwords_filtered, sum(word_freq.values()), len(word_freq)


def create_histogram(word_freq, output_path, source_filename, total_words, unique_words, stopwords_filtered):
    if not word_freq:
        print("No words to plot.")
        return
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(40, 24))
    fig.suptitle(
        "Word Frequency Analysis\n"
        f"Source: {source_filename}\n"
        f"Total words: {total_words:,} | Unique words: {unique_words:,} | Common words filtered: {stopwords_filtered:,}",
        fontsize=16,
        fontweight="bold",
        y=0.995,
    )
    for axis, count, title, fontsize in (
        (ax1, 200, "Top 200 Most Frequent Words", 4),
        (ax2, 1000, "Top 1000 Most Frequent Words", 2),
        (ax3, len(word_freq), f"All {len(word_freq)} Unique Words", 2),
    ):
        data = word_freq.most_common(count)
        if not data:
            continue
        words, freqs = zip(*data)
        axis.bar(range(len(words)), freqs, color="steelblue", edgecolor="black")
        axis.set_xlabel("Words", fontsize=12, fontweight="bold")
        axis.set_ylabel("Frequency", fontsize=12, fontweight="bold")
        axis.set_title(title, fontsize=14, fontweight="bold")
        axis.set_xticks(range(len(words)))
        axis.set_xticklabels(words, rotation=45, ha="right", fontsize=fontsize)
        axis.grid(axis="y", alpha=0.3)
    plt.tight_layout(rect=[0, 0, 1, 0.99])
    plt.savefig(output_path, dpi=700, bbox_inches="tight")
    print(f"Histogram saved to: {output_path}")
    plt.close()


def print_statistics(word_freq, top_n=50):
    total_words = sum(word_freq.values())
    unique_words = len(word_freq)
    print("\n" + "=" * 60)
    print("WORD FREQUENCY ANALYSIS RESULTS")
    print("=" * 60)
    print(f"Total words (after filtering): {total_words:,}")
    print(f"Unique words: {unique_words:,}")
    print("=" * 60)
    print(f"\nTop {top_n} Most Frequent Words:")
    print("-" * 60)
    print(f"{'Rank':<6} {'Word':<25} {'Frequency':<15} {'Percentage':<10}")
    print("-" * 60)
    for rank, (word, count) in enumerate(word_freq.most_common(top_n), 1):
        percentage = (count / total_words) * 100 if total_words else 0
        print(f"{rank:<6} {word:<25} {count:<15,} {percentage:<10.2f}%")


def save_full_word_list(word_freq, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("COMPLETE WORD FREQUENCY LIST\n")
        handle.write("=" * 60 + "\n\n")
        handle.write(f"Total unique words: {len(word_freq):,}\n")
        handle.write(f"Total word count: {sum(word_freq.values()):,}\n\n")
        handle.write("-" * 60 + "\n")
        handle.write(f"{'Word':<30} {'Frequency':<15}\n")
        handle.write("-" * 60 + "\n")
        for word, count in word_freq.most_common():
            handle.write(f"{word:<30} {count:<15,}\n")
    print(f"Complete word list saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze document files (SRT, PDF, TXT) for word frequency.")
    parser.add_argument("path")
    parser.add_argument("--types", nargs="+", default=None)
    parser.add_argument("--top", "-t", type=int, default=50)
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--keep-stopwords", action="store_true")
    parser.add_argument("--save-full-list", action="store_true")
    args = parser.parse_args()

    nlp = None
    if SPACY_AVAILABLE:
        try:
            nlp = spacy.load("es_core_news_sm")
            print("Lemmatization enabled.")
        except OSError:
            print("spaCy model 'es_core_news_sm' not found. Lemmatization disabled.")

    try:
        word_freq, stopwords_filtered, total_words, unique_words = analyze_documents(
            args.path,
            file_types=args.types,
            remove_stopwords=not args.keep_stopwords,
            nlp=nlp,
        )
        source_path = Path(args.path)
        source_filename = source_path.stem if source_path.is_file() else source_path.name
        output_path = args.output or f"./outputs/{source_filename}_word_analysis.png"
        print_statistics(word_freq, args.top)
        create_histogram(word_freq, output_path, source_filename, total_words, unique_words, stopwords_filtered)
        if args.save_full_list:
            save_full_word_list(word_freq, f"./outputs/{source_filename}_full_list.txt")
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
