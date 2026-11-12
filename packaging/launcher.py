"""PyInstaller entry point. Kept outside the package so the spec has a plain script to freeze."""

import os
import sys

# A windowed (no-console) build has no stdout/stderr; logging and print() would fail.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

from immersion_app.app import main

if __name__ == "__main__":
    raise SystemExit(main())
