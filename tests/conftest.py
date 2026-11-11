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

os.environ.setdefault("LINGUALOOP_DATA_DIR", tempfile.mkdtemp(prefix="lingualoop-tests-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
