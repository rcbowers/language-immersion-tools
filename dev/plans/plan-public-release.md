# Plan: Public Release on GitHub

Status: in progress · Created: 2026-11-11 · Last updated: 2026-11-11 (after rename + packaging)

Goal: make Language Immersion Tools ready for a free public release on GitHub. Users should be able to install it from an installer, without cloning the repo or setting up Python.

The project was renamed from LinguaLoop to Language Immersion Tools. The only remaining `LinguaLoop`/`LINGUALOOP_*` strings are deliberate: the legacy data-folder and env-var fallbacks in `core/paths.py`, `core/perf.py`, `auto_miner.py` and `app.py`, their tests, and the old `~/.lingua-loop` path in the changelog history.

---

## Status summary

| Area | State |
|---|---|
| §1 Activity tracker fixes | Done |
| §2 History rewrite, personal data, configurable Anki deck, LICENSE, data folder | Done (history rewritten and pushed; all commits use the noreply address) |
| §3 Async/data-loss fixes, Settings dialog, getting-started panel | Done, except the full `main_window.py` break-up |
| §4 Tests + CI | Done: 665 tests pass; CI green on `master` (Windows + Ubuntu) |
| §5 README/CHANGELOG/templates | Done (installer section added) |
| EPUB support | Merged (PR #3) |
| Merged branches | Deleted locally and on GitHub; only `master` remains |
| §6 Packaging | Set up (see below); first tagged build not yet run on GitHub |
| §7 Auto-miner in the app | Not started; deferred past 0.9.0 |
| Repo visibility | Still PRIVATE |

## Audit blockers (from earlier today)

1. [x] CI red on `master` (spacy): fixed, latest run green.
2. [x] Uncommitted perf/render-cache work: committed. `dev/perf/*.json` (benchmark output) is still tracked; decide whether to keep.
3. [x] `CONTRIBUTING.md` removed, references cleaned.
4. [x] README advertises PDF/EPUB: EPUB merged.
5. [x] Flaky `test_theme_refresh_rerenders_open_pdf`: did not recur (full suite passed 3 times, including the fresh clone).
6. [x] Fresh-clone check (2026-11-11): cloned from GitHub, new venv, `pip install -r requirements-dev.txt`, 665 tests passed, `python -m immersion_app` starts (only an expected "Anki not reachable" warning).

---

## 6. Packaging as an installer (SET UP)

Scope for 0.9.0: **core app only** (PySide6, PyMuPDF, online translation). Offline translation (torch/transformers) and subtitle generation (Whisper, FFmpeg) stay opt-in source-install extras, so the installer stays small (about 370 MB unpacked).

Files:
- `packaging/launcher.py`: PyInstaller entry point (guards against missing stdout/stderr in a windowed build).
- `packaging/immersion.spec`: one-folder windowed build; bundles the Inter fonts and LICENSE; excludes torch, transformers, whisper, matplotlib, spacy.
- `packaging/installer.iss`: Inno Setup script (per-user install by default, Start-menu entry, optional desktop shortcut, uninstaller).
- `packaging/build.ps1`: builds the folder, then the installer if Inno Setup is installed. Output: `dist\LanguageImmersionTools-Setup-<version>.exe`.
- `requirements-build.txt`: PyInstaller + Pillow on top of `requirements.txt`.
- `.github/workflows/release.yml`: on `v*` tags (or manually) runs the tests, checks the tag matches `__version__`, builds the installer and attaches it to the GitHub Release.
- `src/immersion_app/__main__.py`: `python -m immersion_app`. The version shows in *Settings*.

Verified locally: the PyInstaller build succeeds, the frozen exe starts, creates its data folder under `IMMERSION_DATA_DIR`, and the fonts are present in the bundle.

Still to do:
- [ ] Run the release workflow once (manual `workflow_dispatch`) to confirm Inno Setup installs on the runner and the installer works. Install it on a clean machine/VM and open a PDF, an EPUB and a video.
- [ ] App icon: `img/logo.png` is a wide wordmark (3584x1184), so no `.ico` was generated. Drop a square `packaging/icon.ico`; the spec and installer pick it up automatically.
- [ ] Trim size (optional): exclude unused Qt modules (WebEngine, QML, 3D, etc.) from the bundle.
- [ ] FFmpeg check on first run, added to the Getting started checklist (only matters for subtitle generation).
- [ ] Code signing, or keep the SmartScreen note in the README.
- [ ] Decide on macOS/Linux support (`auto_miner.py` uses `msvcrt`; `.bat`/`.ps1` scripts).
- [ ] Optional later: torch-free offline stack (Argos Translate, `faster-whisper`) so offline features can ship in the installer.

---

## 7. Integrate the auto-miner into the app (TO DO, deferred)

The logic is reusable (`core/auto_mining.py`, `core/automine_queue.py`, `media/source_context.py`); the CLI shares the app's Anki settings and data folder.

- [ ] "Batch mine" screen: import words grouped by source (or a markdown file), review matches one at a time, send cards through the app's Anki service.
- [ ] Run source loading and candidate search in a `QRunnable` worker.
- [ ] Unify or clearly separate the two queues in the UI.
- [ ] Move the CLI to a `immersion automine` entry point.

## 3 (remainder). Break up `main_window.py`

About 1,900 lines with 20 `hasattr` guards that protect widget-creation order in `__init__`. Defer; not user-visible.

---

## Release-day steps

1. [x] History rewritten and force-pushed; author addresses are noreply.
2. [x] Merged branches deleted.
3. [x] Fresh-clone check.
4. [ ] Decide on `dev/perf/*.json` (commit or git-ignore).
5. [ ] On your own install, open **Settings** and pick your existing deck (new default is `Language Immersion Tools`). Your old `%APPDATA%\LinguaLoop` folder is copied automatically.
6. [ ] Run the release workflow manually, test the installer.
7. [ ] Optionally delete `archive/git-backup-before-history-rewrite.bundle` (it still contains the copyrighted files from the old history).
8. [ ] Tag `v0.9.0` (move the CHANGELOG *Unreleased* heading to a dated `0.9.0`), let the workflow attach the installer.
9. [ ] Flip the repo to public and confirm the CI badge is green.
