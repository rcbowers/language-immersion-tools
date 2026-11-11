"""Shared pytest setup.

* Puts ``src/`` on ``sys.path`` so ``pytest`` works without ``PYTHONPATH``.
* Points the app's data folder at a throwaway directory *before* any
  ``immersion_app`` module is imported, so tests never touch real user data.
* Defaults Qt to the offscreen platform so tests run headless (CI).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (str(SRC), str(ROOT), str(ROOT / "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("IMMERSION_DATA_DIR", tempfile.mkdtemp(prefix="immersion-tests-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture
def make_epub(tmp_path):
    """Factory fixture: ``make_epub(name="libro.epub", chapters=2, paragraphs=60) -> Path``."""
    from epub_helpers import build_epub

    def _make(name="libro.epub", chapters=2, paragraphs=60):
        return build_epub(tmp_path / name, chapters=chapters, paragraphs=paragraphs)

    return _make
