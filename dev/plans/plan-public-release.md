# Plan: Public Release on GitHub

Status: in progress · Created: 2026-11-11 · Last updated: 2026-11-11

Goal: make LinguaLoop ready for a free public release on GitHub. Users should be able to install it from an installer, without cloning the repo or setting up Python.

Findings came from a code review, a test-suite run, and launching the app against a throwaway data folder (with screenshots).

**Progress (2026-11-11):** §1, §2, §3 (apart from fully breaking up `main_window.py`), §4 and §5 are done on branch `public-release-prep` (commit "Prepare for public release…"). Git history was rewritten to remove copyrighted and personal material; see §2. Still to do: §6 (packaging), §7 (built-in auto-miner), the rest of the `main_window.py` break-up, and the release-day steps at the end of this file.

---

## Suggested order

1. [x] Clean history and remove personal paths (§2). *History rewritten locally; force-push still pending (see "Release-day steps").*
2. [x] Make the Anki deck/note type and the data folder configurable (§2)
3. [x] Fix the activity tracker (§1)
4. [x] Fix the test run and add CI (§4)
5. [x] Rewrite the README and add a LICENSE (§5)
6. [ ] Slim down dependencies and build the installer (§6). *Requirements are split now; packaging not started.*
7. [ ] Build the auto-miner into the app (§7)
8. [ ] Break up `main_window.py` (§3). *Partly done: 2,514 → 1,892 lines, `hasattr` guards 44 → 20.*

---

## 1. Activity tracker: two confirmed bugs plus a design gap (DONE)

### 1a. "Inactive when I'm active": the tracker stops for good after any break (confirmed)

- After 2 idle minutes, `_check_inactivity` closed the session and cleared `_session_start_time`, so every later `record_activity()` returned early. Any time after the first pause went unrecorded.

### 1b. "Active when I'm not": background work counted as user activity (confirmed)

- Every `translation_ready` signal counted, including background prefetches (one request per word on the page in online mode).
- Every `selection_changed` signal counted, and the app fires that itself on every load and page change.

### 1c. Design gap: real reading didn't count

- Scrolling, mouse movement, long reads and paused video didn't count. App dialogs marked the user idle. The indicator only refreshed every 30 s.

### Fix

- [x] Keep the file session open across idle periods and track separate active stretches ("segments") inside it. The next activity starts a new segment.
- [x] Count only `visible=True` translations as activity.
- [x] Remove the `selection_changed` hook. Count real input instead via `gui/activity_monitor.py` (`UserActivityMonitor`, app-level event filter, throttled to 1 event per 5 s).
- [x] Treat focus on the app's own dialogs and tool windows as focused (`QGuiApplication.applicationStateChanged`).
- [x] Refresh the indicator immediately on activity and focus change, plus a 5 s timer (was 30 s).
- [x] Credit time to the calendar day it actually happened (segments are split at midnight).
- [x] Remove the dead `_on_video_loaded_for_usage`.
- [x] Also fixed: reopening a book at a saved page counted the skipped pages as "pages advanced".
- [x] Regression tests: idle → return → activity counts again; restored page; midnight split; focus loss; activity monitor throttling/filtering.
- Doc: `docs/usage-time-tracking.md`.

---

## 2. Must fix before going public (DONE)

- [x] **Copyrighted material in git history.** Removed from all commits with `git filter-repo`:
  - `HP.pdf`, `immersion materials/HP.pdf`
  - old `build/` and `dist/` (PyInstaller output that also embedded local paths)
  - old screenshots/mockups showing book or show text
  - `*.spec` files, a personal YouTube URL list, and the personal `automine_inputs.txt` word list
  - personal paths scrubbed from old file contents with `--replace-text`
  - Verified: no media files, build artefacts, personal paths or book text left in any commit.
  - Pack size is now about 16 MB.
  - A full pre-rewrite backup is in `archive/git-backup-before-history-rewrite.bundle` (git-ignored).
  - `HP2.pdf` moved to `archive/` (ignored).
- [x] **Personal info in the code.**
  - `auto_miner.py` now defaults to `<data folder>/automine_inputs.md`, overridable with the `LINGUALOOP_AUTOMINE_FILE` env var or the `INPUT_FILE` argument. Also new: `--deck`.
  - `scripts/convert_to_h264.ps1` defaults to the current directory.
  - The personal heading in `TODO.md` is gone.
  - Hard-coded Anki install path replaced with `%LOCALAPPDATA%` lookup.
  - The test sentence quoting a copyrighted book was replaced.
- [x] **Hard-coded Anki deck.** `core/anki.py` now has `AnkiSettings` (deck, note type, sentence/translation fields, tags, AnkiConnect URL). It's stored in `user_data["anki"]` and applied with `configure_anki()`.
  - Edited in the new Settings dialog, with lists loaded live from AnkiConnect and a *Create deck* button.
  - `check_anki_setup()` reports *why* Anki isn't ready.
  - `cli/queue.py` and `auto_miner.py` use the same settings.
  - The vocabulary snapshot ignores words from a different deck.
- [x] **LICENSE**: GPL-3.0 (canonical text). Inter's OFL text bundled at `src/immersion_app/gui/fonts/OFL.txt`. Dependency licences listed in the README.
- [x] **googletrans caveat** documented in the README (unofficial, may break or rate-limit; HTTP 429 seen during testing).
- [x] **Data folder.** Moved to the per-user folder via `platformdirs` (`%APPDATA%\LinguaLoop` on Windows), with a `LINGUALOOP_DATA_DIR` override.
  - One-time copy from `<repo>/data` on first start (`paths.migrate_legacy_data`). The old folder is left in place.
  - Previews moved from `~/.lingua-loop` into the data folder.
- [x] **Junk cleaned out.**
  - Deleted: `nul`, `apps/`, root `__pycache__/`, duplicate root docs, and the stale usage-tracking docs (replaced by `docs/usage-time-tracking.md`).
  - Moved to `archive/`: `HP2.pdf`, `spanish_vocab.csv`, `create_output_cards.py` (personal), `android/`.
  - `vocab_counter.py` and `convert_to_h264.ps1` → `scripts/`.
  - `docs/TODO.md` → `dev/TODO.md` (book excerpt removed).
  - Kept `claude.md` and `AGENTS.md`, as requested.

---

## 3. Bugs and fragility (DONE, apart from the full `main_window.py` break-up)

- [x] **Translation availability check freezing the UI**: now `TranslationService.check_availability_async()` on a worker. The saved mode is used immediately, with automatic fallback when unavailable. Toggling re-checks in the background. The offline check no longer imports torch.
- [x] **AnkiConnect timeouts**: 10 s per request, 60 s for bulk vocabulary fetches.
- [x] **Anki add / queue processing on the UI thread**: moved to workers (`add_card_async`, `process_queue_async`) with double-submit guards. Connection drops during an add queue the card.
- [x] **Worker errors silently swallowed** (found during the work): tasks caught `RuntimeError` around the whole job, so AnkiConnect errors ("duplicate note") and translation errors vanished and the UI got stuck. Now only the emit is guarded (`core/signals.safe_emit`).
- [x] **Data-loss risks** (found during the work):
  - Background saves ran on the shared pool and could finish out of order. They now use a single-thread save queue.
  - The final save could be lost on exit. It's now flushed synchronously in `closeEvent`.
  - The prefetch preference was dropped on every load.
- [x] **Shutdown crashes** with translations in flight: pools are cleared and drained on close. Prefetch failures log one line instead of a traceback.
- [~] **`main_window.py` size and `hasattr` guards**:
  - Removed the dead duplicate translation pipeline and duplicate classes, plus the legacy PDF/video/add/queue bodies behind `if hasattr(self, "<x>_controller")`.
  - Ported their tests to the controllers (`tests/gui/test_mining_controller.py`, `test_pdf_controller_navigation.py`, `test_video_controller.py`).
  - 2,514 → 1,892 lines; 44 → 20 `hasattr` guards.
  - **Remaining:** the 20 guards protect widget-creation order during `__init__`. Removing them safely is part of the full break-up (still to do).
- [x] **UI issues from the screenshots:**
  - [x] Duplicate open buttons: the welcome screen hides the top-bar Recent/Open/title, and *Open PDF or video…* is the primary button near the top.
  - [x] "No document loaded" white box: fixed at the root cause. The command-bar stylesheet cascaded to every child label; it's now scoped by object name.
  - [x] Library empty state: centred, outside the flow layout, smaller minimum height.
  - [x] Settings gear: replaced by a labelled *Settings* button (Ctrl+,).
  - [x] Page box shows `/ total`.
  - [x] Empty space: the welcome page scrolls instead of squashing, the Recent section is hidden until something is opened, margins tightened.
  - [x] Hard-coded colours in the status indicators replaced by new `Theme.SUCCESS/WARNING/DANGER` tokens.
- [x] **Real Settings dialog** (`gui/widgets/settings_dialog.py` + `gui/controllers/settings_controller.py`) covering Anki, languages, online/offline translation, pre-translation, appearance, and the data folder (shown, with an Open button; relocation via `LINGUALOOP_DATA_DIR`).
- [x] **First-run experience**: a *Getting started* checklist on the welcome screen (`gui/widgets/getting_started_panel.py`).
  - Anki status says whether Anki is unreachable or the deck/note type/fields are wrong, and offers *Start Anki* or *Settings…*.
  - Also shows the chosen languages and the first-open step.
  - Hideable, and hides itself once complete.
  - *Not done:* an FFmpeg check (only matters for subtitle generation).
- [x] *Open data folder* works on macOS/Linux (was `explorer` only).

---

## 4. Tests (DONE)

Result now: **254 passed, 0 failed.** Plain `python -m pytest` works with no flags or `PYTHONPATH`.

- [x] `tests/test_logging_standalone.py` and `tests/verify_refactor.py` removed: script-style duplicates of existing tests.
- [x] `beautifulsoup4` and `pytest-qt` added to `requirements-dev.txt`.
- [x] Anki analytics test made date-independent (`AnkiAnalyticsManager(today=...)`).
- [x] `test_pdf_controller` fake gained `merge_highlight_bboxes`. The status-bar order test was updated.
- [x] `test_completion_feature.py` no longer returns a value. The deprecated `QMouseEvent` constructor was replaced.
- [x] `tests/conftest.py`: puts `src/` on the path, uses a throwaway `LINGUALOOP_DATA_DIR`, and runs Qt offscreen, so tests can never touch real user data. Plus `pytest.ini`.
- [x] Dev dependencies split into `requirements-dev.txt`. Runtime requirements split into `requirements.txt` (core), `requirements-offline.txt` and `requirements-media.txt`.
- [x] CI: `.github/workflows/tests.yml` runs pytest on Windows and Ubuntu (Python 3.12), plus an informational pyflakes step. *Not yet run on GitHub; it will run on the first push.*
- [x] New tests:
  - tracker regressions, activity monitor
  - Settings dialog/controller, Anki settings parsing
  - data-folder resolution and migration
  - ordered saves/flush and user-data normalisation
  - mining-controller async add/queue flows
  - PDF controller navigation/render against a generated PDF
  - subtitle click/phrase selection, `auto_miner` defaults and `--deck`

---

## 5. Docs (DONE)

- [x] README rewritten for end users:
  - what it does, with screenshots (`docs/screenshots/`, generated from an original sample text, not copyrighted material)
  - install steps, AnkiConnect setup (code 2055492159), first-run and deck setup
  - FFmpeg, online vs offline translation (with privacy note and download size)
  - a full shortcut table, the queue and study-time explanation, the data folder
  - companion tools, troubleshooting, licences
- [x] `CONTRIBUTING.md` (setup, tests, architecture in one minute, PR checklist). Issue templates (bug, feature) and a PR template under `.github/`.
- [x] Architecture docs stay in `docs/` and are linked from CONTRIBUTING. `docs/architecture.md` was updated for the data folder, settings and tracking.
- [x] `CHANGELOG.md` at the root:
  - an *Unreleased: 0.9.0, first public release* section in Keep-a-Changelog style
  - the previous dated log kept under "Development history"
  - `AGENTS.md` now points to it
- [x] Fonts README updated (bundled, OFL included).

---

## 6. Packaging as an installer (TO DO)

The blocker is size. `torch`, `transformers` and `openai-whisper` add several GB. The current `build_exe.bat` uses the old name and won't pick up the fonts or logo.

- [~] Optional extras: done at the requirements level (`requirements-offline.txt`, `requirements-media.txt`). Still to do: a `pyproject.toml` with a `lingualoop` entry point and extras.
- [ ] Swap in lighter libraries that don't need torch: Argos Translate (ctranslate2) instead of MarianMT, and `faster-whisper` instead of `openai-whisper`. Download models on demand into the data folder.
- [ ] PyInstaller **one-folder** build with a `.spec` that bundles fonts, images and the Qt multimedia/FFmpeg plugins. Replace `build_exe.bat`.
- [ ] **Inno Setup** installer (Start-menu shortcut, uninstaller, per-user install).
- [ ] GitHub Action: build on tag push and attach to the Release.
- [ ] Bundle FFmpeg, or check for it on first run (add to the Getting started checklist).
- [ ] Mention the SmartScreen warning for unsigned exes in the README, or consider code signing.
- [ ] Add `__version__` (0.9.0) and show it in the app. The changelog already uses 0.9.0.
- [ ] Decide on macOS/Linux support (`auto_miner.py` uses `msvcrt`; `.bat`/`.ps1` scripts).
- Note: the frozen-build data-folder problem is already solved (`platformdirs`; no writes next to the exe).

---

## 7. Integrate the auto-miner into LinguaLoop (TO DO)

**Recommendation: yes.** The logic is already reusable (`core/auto_mining.py`, `core/automine_queue.py`, `media/source_context.py`). The hard-coded vault path is gone, and the CLI now shares the app's Anki settings and data folder.

- [ ] Add a "Batch mine" screen in the app:
  1. Paste or import words grouped by source, or point it at a markdown file.
  2. Review matches one card at a time with the CLI's keys.
  3. Send cards through the app's Anki service.
- [ ] Run source loading and candidate search in a `QRunnable` worker.
- [ ] Unify or clearly separate the two queues in the UI.
- [x] Keep the CLI with the input file as an argument and no hard-coded default path. *(Done; it currently stays at the repo root as `auto_miner.py`. Move it to `lingualoop automine` when the pyproject entry points exist.)*

---

## Release-day steps (TO DO, need you)

1. Review the branch `public-release-prep`, then merge it into `master` (or make it the new `master`).
2. **Force-push the rewritten history**: `git push --force origin master` (plus `public-release-prep` if you want it on GitHub).
   - Every commit hash changed, so any other clone must be re-cloned.
   - `filter-repo` turned the remote branch `claude/android-pdf-app-design-hDDy0` into a local branch. Decide whether to delete it on GitHub (`git push origin --delete claude/android-pdf-app-design-hDDy0`) or force-push its rewritten version.
3. **Optional privacy step:** the commits carry your personal Gmail address as author email. To publish under GitHub's no-reply address instead, rewrite authors with `git filter-repo --mailmap` *before* force-pushing.
4. On first launch after upgrading, open **Settings** and pick your existing deck. The new default is `LinguaLoop`, not the old hard-coded deck name. Your `data/` folder is copied to `%APPDATA%\LinguaLoop` automatically.
5. If you keep the auto-miner word list in a notes vault, set `LINGUALOOP_AUTOMINE_FILE` to that file.
6. Make the repo public; check that the CI run passes on GitHub.
7. Optionally delete `archive/git-backup-before-history-rewrite.bundle` once you're happy (it still contains the old history, including the copyrighted files).
