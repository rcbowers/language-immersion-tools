"""Extract mineable text contexts from supported source documents."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Callable
from urllib.parse import urlparse

from immersion_app.core.automine_queue import is_url
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


_SKIPPED_TAGS = frozenset(
    {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "head"}
)
_BLOCK_TAGS = frozenset(
    {"p", "div", "br", "li", "ul", "ol", "section", "article", "main", "blockquote", "tr",
     "h1", "h2", "h3", "h4", "h5", "h6"}
)
_URL_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_URL_TIMEOUT_SECONDS = 15


class _PageTextParser(HTMLParser):
    """Collect a page's title and visible text, split into block-level paragraphs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._skip_depth = 0
        self._in_title = False
        self._article_depth = 0
        # Text is gathered twice: everything, and only inside <article>/<main>.
        self._all: list[str] = [""]
        self._article: list[str] = [""]

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title":
            self._in_title = True
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
            return
        if tag in {"article", "main"}:
            self._article_depth += 1
        if tag in _BLOCK_TAGS:
            self._break()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in _SKIPPED_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag in {"article", "main"}:
            self._article_depth = max(0, self._article_depth - 1)
        if tag in _BLOCK_TAGS:
            self._break()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._skip_depth:
            return
        self._all[-1] += data
        if self._article_depth:
            self._article[-1] += data

    def _break(self) -> None:
        self._all.append("")
        self._article.append("")

    def paragraphs(self) -> list[str]:
        blocks = self._article if any(block.strip() for block in self._article) else self._all
        return [cleaned for block in blocks if (cleaned := _clean_text(block))]


def _fetch_html(url: str) -> str:
    try:
        import requests
    except ImportError as exc:  # pragma: no cover - declared project dependency
        raise RuntimeError("requests is required to read web page sources.") from exc

    try:
        response = requests.get(
            url, headers={"User-Agent": _URL_USER_AGENT}, timeout=_URL_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"Could not download {url}: {exc}") from exc
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding
    return response.text


def extract_url_contexts(url: str, *, fetch: Callable[[str], str] | None = None) -> list[SourceContext]:
    """Extract sentence contexts from a web page's visible text, grouped by paragraph."""
    parser = _PageTextParser()
    parser.feed((fetch or _fetch_html)(url))
    parser.close()

    source_name = _clean_text(parser.title) or urlparse(url).netloc or url
    contexts: list[SourceContext] = []
    for paragraph_index, paragraph in enumerate(parser.paragraphs(), start=1):
        for sentence in _sentences(paragraph):
            contexts.append(SourceContext(sentence, source_name, f"Paragraph {paragraph_index}"))
    return contexts


def load_source_contexts(path: str | Path) -> list[SourceContext]:
    """Load contexts from a web page URL, or a PDF or SRT source document."""
    if is_url(str(path)):
        return extract_url_contexts(str(path))
    source_path = Path(path)
    if not source_path.is_file():
        raise FileNotFoundError(f"Source document does not exist: {source_path}")
    if source_path.suffix.lower() == ".pdf":
        return extract_pdf_contexts(source_path)
    if source_path.suffix.lower() == ".srt":
        return extract_srt_contexts(source_path)
    raise ValueError("Unsupported source document. Use a .pdf or .srt file.")
