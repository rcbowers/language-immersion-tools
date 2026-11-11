# Plan: Public Release on GitHub

Status: proposed · Created: 2026-11-11

Goal: make LinguaLoop ready for a free public release on GitHub. Users should be able to install it from an installer, without cloning the repo or setting up Python.

Findings come from a code review, a test-suite run, and launching the app against a throwaway data folder (with screenshots). No code has been changed yet.

---

## Suggested order

1. [ ] Clean history and remove personal paths (§2)
2. [ ] Make the Anki deck/note type and the data folder configurable (§2)
3. [ ] Fix the activity tracker (§1)
4. [ ] Fix the test run and add CI (§4)
5. [ ] Rewrite the README and add a LICENSE (§5)
6. [ ] Slim down dependencies and build the installer (§6)
7. [ ] Build the auto-miner into the app (§7)
8. [ ] Break up `main_window.py` (§3)

---

## 1. Activity tracker: two confirmed bugs plus a design gap

### 1a. "Inactive when I'm active": the tracker stops for good after any break (confirmed)

- After 2 idle minutes, `_check_inactivity` closes the session and `_reset_session_state()` clears `_session_start_time`.
- From then on, `record_activity()` exits early because `_session_start_time is None` (`src/immersion_app/core/usage_time_tracker.py`, in `record_activity`).
- So after the first break, clicks, page turns and playback are ignored until the file is reopened. Any time after the first pause goes unrecorded, and the indicator stays idle.
- Repro (confirmed with a script): load a doc, record activity, backdate the buffer 3 minutes, call `_check_inactivity()`, then `record_activity()`. Result: `active: False, buffer: 0`.

### 1b. "Active when I'm not": background work counts as user activity (confirmed)

- `main_window.py:471` connects every `translation_ready` signal to `record_activity()`, including background prefetches (`visible=False`).
  - In online mode, `TranslationService.prefetch_async` fires one `translate_async` per word on the page. Each reply arrives over the following seconds or minutes and counts as activity, so the user goes "active" without touching anything.
  - The prefetch also sends hundreds of requests to Google per page, which risks rate-limiting or an IP block.
- `main_window.py:470` connects every `selection_changed` signal to `record_activity()`, and the app fires that itself: `mining_controller.clear_selection()` runs on every PDF load and page change. In testing the indicator turned green as soon as the PDF loaded, with no user input.

### 1c. Design gap: real reading doesn't count

These don't count as activity:
- scrolling
- mouse movement
- reading a dense page for more than 2 minutes without clicking
- sitting on a paused video

Also:
- Opening any app dialog (Queue, Activity, message boxes) takes focus from the main window (`changeEvent` → `ActivationChange` → `isActiveWindow()`), which marks the user idle.
- The indicator only refreshes on a 30-second timer.

### Fix

- [ ] Keep the file session open across idle periods and track separate active stretches inside it, instead of finalizing and wiping the session.
- [ ] Count only `visible=True` translations as activity.
- [ ] Remove the `selection_changed` → `record_activity` hook. Count real input instead (application-level event filter for mouse press/move, wheel/scroll, key press), throttled to about 1 event per 5–10 s.
- [ ] Treat focus on the app's own dialogs and tool windows (popover, shortcut panel) as focused.
- [ ] Refresh the indicator immediately on activity and on focus change, not just every 30 s.
- [ ] Credit time to the calendar day it actually happened (sessions that run past midnight currently count on the start day).
- [ ] Remove the dead `_on_video_loaded_for_usage` (`main_window.py:1826`).
- [ ] Regression tests: idle → return → activity counts again; background prefetch doesn't mark active; dialog focus doesn't mark idle.

---

## 2. Must fix before going public

- [ ] **Copyrighted material in git history.** Harry Potter PDFs (`immersion materials/HP.pdf` is tracked even though `.gitignore` excludes the folder), plus old `dist/*.exe` and `build/` files, are all in history. The repo is still private, so the cleanest fix is to publish a fresh repo or squash history rather than editing history file by file. Also delete the untracked `HP2.pdf` from the working tree.
- [ ] **Personal info in the code.**
  - `auto_miner.py` hard-codes two absolute paths to personal Obsidian vaults (`DEFAULT_INPUT_FILE`).
  - `convert_to_h264.ps1` has a personal absolute default path.
  - `TODO.md` has a personal note heading.
  - Replace with arguments or config, and grep for `C:/Users` / `C:\Users` before publishing.
- [ ] **Hard-coded Anki deck.** `src/immersion_app/core/anki.py` sets `DECK_NAME = "2025 Spanish Immersion"`, `MODEL_NAME = "Basic"`, fields `Front`/`Back`, and the AnkiConnect URL. Every other user's Anki check will fail. Make these settings, picked from AnkiConnect's `deckNames` / `modelNames` / `modelFieldNames`, with a mapping for the sentence and translation fields.
- [ ] **No LICENSE file**, so nobody can legally reuse the code. Pick one (MIT, GPL-3.0, etc.) and check compatibility with dependencies (PySide6 is LGPL; PyMuPDF is AGPL/commercial, which matters for distributing binaries).
- [ ] **googletrans caveat.** It's an unofficial Google scraper that breaks from time to time. Say so in the README and fail gracefully.
- [ ] **Data folder sits inside the source tree** (`core/paths.py`: `PROJECT_ROOT / "data"`). In a packaged exe that's read-only (Program Files) or temporary (PyInstaller one-file temp dir), so data would be lost or fail to save. Move it to a per-user data folder (`%APPDATA%\LinguaLoop` via `platformdirs`), with a one-time migration from `./data`. The same applies to `auto_miner.py`'s `RECENT_SOURCES_PATH`.
- [ ] **Junk to clean out:**
  - stray `nul` file, `HP2.pdf`, `spanish_vocab.csv`
  - leftover `apps/` folder (only `__pycache__` / empty test dirs)
  - root `__pycache__/`
  - duplicate docs in the root and `docs/` (`TODO.md`, `USAGE_TIME_TRACKING_IMPLEMENTATION.md`, `USAGE_TRACKING_INDICATOR.md`)
  - `claude.md` and `AGENTS.md` (internal agent notes; move to `dev/` or drop)
  - `android/` (half-built; remove it or mark it experimental)
  - loose root scripts (`create_output_cards.py`, `vocab_counter.py`, `convert_to_h264.ps1`): move into `src/immersion_app/cli/` or `scripts/`

---

## 3. Bugs and fragility

- [ ] **The UI freezes while checking translation availability.** `TranslationService.is_mode_available()` runs on the UI thread (`main_window.py:1419-1449`). It opens a socket to `8.8.8.8:53` with a 2-second timeout and then calls the backend's own availability check. Offline mode can also load torch at that point. This happens at startup and on every translation-mode toggle. Move it to a `QRunnable` worker and update the badge when it finishes.
- [ ] **AnkiConnect calls have no timeout** (`anki.py`, `anki_connect_invoke` → `urllib.request.urlopen(...)`). If Anki hangs, those calls hang with it. Add a timeout of a few seconds.
- [ ] **`main_window.py` is about 2,500 lines and checks `hasattr(...)` 44 times.** Those checks mean setup order is fragile and quietly skips things, which is a big part of why the UI feels brittle. Controllers also reach into `self.window.*` directly. Per `AGENTS.md`, extract services and controllers and pass explicit dependencies, so these checks aren't needed.
- [ ] **UI issues from the screenshots:**
  - "Recent", "Open…" and "Open Source" do overlapping jobs. Consolidate.
  - The "No document loaded" title sits in a white box in light mode.
  - The "Library" empty-state text is pushed to the left instead of centered.
  - The settings gear is barely visible in light mode.
  - The page box shows "6" with no "of 146".
  - The welcome screen has a lot of empty space; a first-run checklist could go there (see below).
- [ ] **"Settings" isn't a settings dialog.** It's a menu stub (`main_window.py:985` has a `TODO` saying so). There's nowhere to set the deck, card fields, data folder or AnkiConnect URL. Build a real Settings dialog covering:
  - Anki deck and note type, plus field mapping
  - AnkiConnect URL
  - learning and native language
  - online/offline translation, and whether to prefetch
  - data folder location
  - appearance
- [ ] **First-run experience.** Add a short checklist:
  - Is AnkiConnect reachable? (show the add-on code `2055492159`)
  - Pick a deck
  - Pick languages
  - Is FFmpeg available?

---

## 4. Tests

Current result (with workarounds): **216 passed, 3 failed, 5 errors.** The full `pytest tests` run won't start without exclusions.

- [ ] `tests/test_logging_standalone.py` calls `exit(1)` when it's imported, which aborts the whole run. Convert it to real tests or move it out of `tests/`.
- [ ] `tests/verify_refactor.py` is a script, not a test. Move it out of `tests/`.
- [ ] `tests/test_vocab_counter.py` needs `bs4` (`beautifulsoup4`), which isn't in the requirements.
- [ ] `pytest-qt` (the `qtbot` fixture) isn't in the requirements, which causes the 5 errors (`test_completion_tracker`, `test_usage_time_integration`).
- [ ] `tests/core/test_anki_analytics_manager.py::test_record_successful_card_add_updates_counts_and_vocabulary` depends on today's date: the signal emits `today_count()` for the real date. Inject a clock or a date.
- [ ] `tests/test_pdf_controller.py::test_click_updates_selection_and_requests_translation` calls `merge_highlight_bboxes`, which doesn't exist on the test's fake PDF service.
- [ ] `tests/test_pdf_ui.py::test_pdf_status_bar_right_side_order_is_translation_anki_zoom` expects an older status-bar order (the usage indicator `○` now comes first).
- [ ] `tests/test_completion_feature.py` returns a bool instead of asserting (pytest warning).
- [ ] Split dev dependencies (`pytest`, `pytest-qt`) out of runtime `requirements.txt`, e.g. `pyproject.toml` optional dependencies `[dev]`.
- [ ] Add CI: a GitHub Actions workflow running `pytest` with `QT_QPA_PLATFORM=offscreen` on Windows, plus Linux if supported.

---

## 5. Docs

- [ ] The README tells you to run `run_sentence_miner_gui.bat`, which doesn't exist (the real one is `run_lingualoop.bat`).
- [ ] Rewrite the README for end users. Missing today:
  - what the app does, with screenshots or a GIF
  - download/install instructions (link to Releases)
  - AnkiConnect install steps (add-on code `2055492159`)
  - which deck and note type to create, and how to configure them
  - FFmpeg setup for video and subtitles
  - what online vs offline translation means, and the download size of offline models
  - a keyboard-shortcut reference
  - privacy: online mode sends words to Google
  - supported languages and platforms
- [ ] Add `CONTRIBUTING.md` (dev setup, running tests, architecture pointer) and issue/PR templates.
- [ ] The architecture doc (`docs/architecture_design_readme.md`) is detailed but more useful to contributors than to users. Keep it under `docs/` or `dev/` and link it from CONTRIBUTING.
- [ ] Tidy `docs/changelog.md` into a user-facing `CHANGELOG.md` with version numbers.

---

## 6. Packaging as an installer

The blocker is size. `torch`, `transformers` and `openai-whisper` add several GB, and a PyInstaller build that includes them would be huge and slow. The current `build_exe.bat` also uses the old name and won't pick up the font files (`src/immersion_app/gui/fonts`) or the logo (`img/`).

- [ ] Add a `pyproject.toml` with a `lingualoop` entry point, and make offline translation and subtitle generation optional add-ons.
- [ ] Swap in lighter libraries that don't need torch:
  - Argos Translate (ctranslate2) instead of MarianMT. `language_config.py` already has `argos` codes, so this may have been the plan.
  - `faster-whisper` instead of `openai-whisper`.
  - Download models on demand, into the user data folder.
- [ ] Build with PyInstaller in **one-folder** mode (it starts faster than one-file and antivirus flags it less) using a `.spec` file that includes the fonts, images and Qt multimedia/FFmpeg plugins.
- [ ] Wrap it in an **Inno Setup** installer (Start-menu shortcut, uninstaller, per-user install so no admin is needed).
- [ ] Have a GitHub Action build it on tag push and attach it to each Release.
- [ ] Bundle FFmpeg, or check for it on first run with a helpful message.
- [ ] Unsigned exes trigger a SmartScreen warning. Mention that in the README, or consider code signing later.
- [ ] Add a version number (`__version__`) and show it in the app.
- [ ] Decide on macOS/Linux support. The current code is Windows-leaning (`auto_miner.py` uses `msvcrt`, `.bat`/`.ps1` scripts).

---

## 7. Integrate the auto-miner into LinguaLoop

**Recommendation: yes.**

The logic is already reusable: `core/auto_mining.py`, `core/automine_queue.py` and `media/source_context.py` hold it, and `auto_miner.py` is mostly a terminal interface on top. In its current form it doesn't work as a public feature:
- it's Windows-only (it reads keys with `msvcrt`)
- it's hard-wired to a personal Obsidian vault
- it needs a terminal and Python, which people installing an exe won't have

Two queues also confuse things: the app's JSON card queue (`data/queue/queued_cards.json`) and the markdown queue of words with their sources (`# <source>` sections).

Plan:
- [ ] Add a "Batch mine" screen in the app:
  1. Paste or import words grouped by source (local PDF/SRT path or URL), or point it at a markdown file.
  2. Review the matches one card at a time, with the same keys as the CLI: Enter to add, E to edit, arrows to pick an occurrence, `,` and `.` to move the sentence boundaries.
  3. Cards go out through the app's existing Anki service (and its configurable deck).
- [ ] Run source loading and candidate search in a `QRunnable` worker, per the architecture rules.
- [ ] Unify or clearly separate the two queues in the UI.
- [ ] Keep the CLI as `lingualoop automine` for power users, with the input file given as an argument (no hard-coded default path).
