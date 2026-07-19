"""Extract mineable text contexts from supported source documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from immersion_app.media.subtitle_parser import SRTParser


@dataclass(frozen=True)
class SourceContext:
    """A visible source passage and its human-readable location."""

    text: str
    source_name: str
    location: str


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sentences(text: str) -> list[str]:
    """Return punctuation-delimited sentences, preserving a final fragment."""
    return [
        cleaned
        for match in re.finditer(r"[^.!?…]+(?:[.!?…]+|$)", text, flags=re.DOTALL)
        if (cleaned := _clean_text(match.group(0)))
    ]


def _format_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def extract_pdf_contexts(path: str | Path) -> list[SourceContext]:
    """Extract sentence contexts from a text-based PDF, grouped by page."""
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - declared project dependency
        raise RuntimeError("PyMuPDF is required to read PDF source documents.") from exc

    source_path = Path(path)
    contexts: list[SourceContext] = []
    with fitz.open(source_path) as document:
        for page_index, page in enumerate(document):
            for sentence in _sentences(page.get_text("text") or ""):
                contexts.append(SourceContext(sentence, source_path.name, f"Page {page_index + 1}"))
    return contexts


def extract_srt_contexts(path: str | Path) -> list[SourceContext]:
    """Extract one context per subtitle cue, located by its start timestamp."""
    source_path = Path(path)
    parser = SRTParser.from_file(source_path)
    contexts: list[SourceContext] = []
    for subtitle in parser.subtitles:
        visible_text = re.sub(r"<[^>]+>", "", subtitle.text)
        if cleaned := _clean_text(visible_text):
            contexts.append(
                SourceContext(cleaned, source_path.name, _format_timestamp(subtitle.start_ms))
            )
    return contexts


def load_source_contexts(path: str | Path) -> list[SourceContext]:
    """Load contexts from a PDF or SRT source document."""
    source_path = Path(path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Source document does not exist: {source_path}")
    if source_path.suffix.lower() == ".pdf":
        return extract_pdf_contexts(source_path)
    if source_path.suffix.lower() == ".srt":
        return extract_srt_contexts(source_path)
    raise ValueError("Unsupported source document. Use a .pdf or .srt file.")
