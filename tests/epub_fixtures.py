"""Fixtures used only by EPUB-focused tests."""

from __future__ import annotations

import pytest

from epub_helpers import build_epub


@pytest.fixture
def make_epub(tmp_path):
    """Build a synthetic EPUB under the test's temporary directory."""

    def _make(name="libro.epub", chapters=2, paragraphs=60):
        return build_epub(tmp_path / name, chapters=chapters, paragraphs=paragraphs)

    return _make
