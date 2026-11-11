# Changelog

All notable changes to Language Immersion Tools. Versions follow [semantic versioning](https://semver.org/).

## [Unreleased] - 0.9.0, first public release

### Added
- **Five new color themes** in *Settings → Appearance*: Sepia, Forest, Nord, Solarized Dark and Midnight (OLED), alongside Light and Dark. Dark themes also invert PDF pages.
- **Settings dialog** (Settings button or Ctrl+,): Anki deck, note type, sentence/translation fields, tags and AnkiConnect URL, loaded live from Anki, with a *Create deck* button. Also learning/native language, online/offline translation, background pre-translation, appearance and the data folder.
- **Getting started checklist** on the welcome screen: shows whether Anki is reachable and set up correctly (with *Start Anki*), your languages, and how to open your first source.
- Page counter shows the total (`12 / 146`).
- `auto_miner.py --deck` and the `IMMERSION_AUTOMINE_FILE` environment variable. Both CLIs now use the Anki settings chosen in the app.
- GPL-3.0 license, contributor guide, GitHub issue/PR templates and a CI workflow.

### Changed
- **Renamed from LinguaLoop to Language Immersion Tools.** Your data folder is copied from `%APPDATA%\LinguaLoop` to `%APPDATA%\LanguageImmersionTools` on first start (the old folder is left in place). The `LINGUALOOP_DATA_DIR`, `LINGUALOOP_AUTOMINE_FILE` and `LINGUALOOP_PERF` environment variables still work, but are now `IMMERSION_DATA_DIR`, `IMMERSION_AUTOMINE_FILE` and `IMMERSION_PERF`. New installs default to the `Language Immersion Tools` Anki deck and tag; existing settings are unchanged. The launcher is now `run_immersion.bat`.
- **Your data moved** out of the source folder into a per-user folder (`%APPDATA%\LanguageImmersionTools` on Windows). Existing `data/` contents are copied over automatically on first start. Override with `IMMERSION_DATA_DIR`.
- The Anki deck is no longer hard-coded. New installs default to a `Language Immersion Tools` deck with the `Basic` note type. **If you upgraded, open Settings once and pick your existing deck.**
- Test suite grew from 254 to about 600 tests (line coverage 48% to 73%), covering the Anki/translation mining path, the card queue, recent files, controllers and a main-window smoke test. CI now prints a coverage report (no failure threshold yet).
- Adding a card and processing the queue now run in the background, so a slow or busy Anki no longer freezes the window.
- Checking whether online/offline translation is available no longer blocks the window at startup or when toggling.
- Welcome screen: primary *Open PDF or video…* button near the top, no duplicate Open/Recent buttons, a centred library empty state, and the page scrolls instead of squashing on small windows.
- The settings gear is now a labelled *Settings* button. The title in the top bar no longer sits in a white box.
- Requirements are split: `requirements.txt` (core), `-offline`, `-media` and `-dev`.
- **PDF reading is much more responsive.** Clicking or Ctrl+hovering a word only moves a highlight overlay instead of re-rendering the whole page (about 10x faster). Pages now render in the background, recently viewed and neighbouring pages are cached, and page turns no longer rewrite your data folder's directory structure or rebuild the (hidden) library grid.

### Fixed
- Switching theme or finishing the Anki vocabulary sync did not refresh word highlights on an open PDF.
- Pressing Ctrl+Return after a failed translation could add an Anki card (or queue one) with `Translation error: ...` as its back. Cards now need a real translation.
- **Study-time tracker**: time stopped being counted for good after the first 2-minute break. It now resumes on your next action.
- **Study-time tracker**: background work (page pre-translation, selection resets) made the indicator show *active* when you weren't doing anything. Only real input (mouse, scrolling, keys), visible translations and video playback count now.
- Study time no longer pauses while you're in one of the app's own dialogs, the indicator updates within seconds, time after midnight counts toward the new day, and reopening a book at a saved page no longer counts as pages read.
- Anki errors such as *duplicate note* and translation backend errors were silently swallowed, leaving the UI stuck. They're now shown.
- AnkiConnect requests now time out instead of hanging forever.
- Background saves could finish out of order (older data overwriting newer), and the last save could be lost on exit. Saves are now ordered and flushed when the app closes.
- The *pre-translate* preference was reset on every restart.
- Words from a previous deck's snapshot are no longer highlighted after switching decks.
- Closing the app while translations were in flight printed thread errors.
- *Open data folder* works on macOS and Linux.

### Removed
- About 600 lines of dead duplicate translation, PDF and video code from the main window.

## Development history (pre-release)

### 2026-10-17

#### Automatic Miner Sources Now Come From the Queue File

- The queue file is now a markdown file (`automine_inputs.md`); its format is unchanged.
- `automine_inputs.txt` is grouped into `# <source>` sections; the source is a local PDF/SRT path (optionally quoted) or a web URL, and the lines below it are mined from that source. Approved words are removed from their own section only.
- Web page sources are downloaded and split into sentence contexts by paragraph (`extract_url_contexts`); a source that fails to load is skipped with a warning.
- A `# none ...` section takes pasted sentences with the target word in `[brackets]`; each line is its own context and no source is loaded.
- The recent-sources picker and the `SOURCE_DOCUMENT` argument are disabled (code kept). `auto_miner.py [INPUT_FILE]` is the only form.

### 2026-09-23

#### Added In-Terminal Queue Editor to Automatic Miner

- Launching `auto_miner.py` now opens a terminal text editor pre-filled with `automine_inputs.txt`, instead of requiring the queue to be edited separately before running.
- Supports typing, arrow-key navigation, and Enter for new lines; Ctrl+S saves the queue and transitions straight into mining.

### 2026-09-07

#### Improved Automatic Miner Card Preview

- Renders the proposed front and back in a bordered, Anki-style terminal card during interactive review.
- Wraps long content to a responsive card width while preserving ANSI highlighting and geometric alignment.

### 2026-09-02

#### Improved Automatic Miner

- Starts Anki automatically when it is not already running, then waits for AnkiConnect before mining.
- Adds keyboard context-window editing during review: `,`/`.` move the start one word, and `<`/`>` move the end one word without excluding the mined phrase.
- Shows up to five words before and after the active context window in gray on the same `front:` line; those words can be added to the card context with the window controls.
- Updates the Google Translate dependency pins to a compatible modern `googletrans`/`httpx` stack, fixing the `httpcore.SyncHTTPTransport` import failure.
- Surfaces Google Translate HTTP failures instead of accepting `googletrans`'s source-text fallback, so auto-miner cannot create a card with an untranslated back.
- Falls back to the local MarianMT translator for the rest of an auto-miner session after Google Translate fails; its model is downloaded only when needed.

### 2026-05-12

#### Added Content Browser to Welcome Page

Implemented a visual content browser with thumbnail previews on the welcome page to complement the existing recent files list. Files are automatically added to the library when opened via any method (Ctrl+O, recent files, or grid).

Added:
- `ContentBrowserManager` (`core/content_browser_manager.py`) - State manager for imported content library with signal-based updates
- `PreviewGenerator` (`core/preview_generator.py`) - Async thumbnail generation service for PDFs (first page) and videos (frame at 1 second) with disk caching
- `ContentBrowserItem` (`gui/widgets/content_browser_item.py`) - 180x240px grid card widget with preview, filename, and metadata (page count/duration)
- `ContentBrowserGrid` (`gui/widgets/content_browser_grid.py`) - Responsive grid container with FlowLayout that wraps items to window width
- Right-click context menu to remove items from library
- Library section on welcome page with visual grid below recent files

Changed:
- PDFController and VideoController now add opened files to content browser automatically
- Welcome page layout optimized for taller content sections with reduced margins and spacing
- Content browser stored in `user_data["imported_content"]` with preview cache in `~/.lingua-loop/data/previews/`

Features:
- Click grid items to open content at last reading/viewing position
- Dark mode support with automatic theme refresh
- Empty state handling when no content imported
- All styling from Theme constants following architecture patterns

Test Coverage:
- Added 32 new tests (18 core, 14 GUI) - all passing
- `tests/core/test_content_browser_manager.py` - State management and signal emission
- `tests/core/test_preview_generator.py` - Async preview generation and caching
- `tests/gui/test_content_browser_widgets.py` - Widget behavior and user interactions

#### Main Window Refactor Cutover

Refactored LinguaLoop's `main_window.py` around extracted services, controllers, and helper widgets so the window is no longer the primary owner of translation, PDF, video/subtitle, and queue workflows.

Added:
- `TranslationService` for translation cache ownership, backend mode/language switching, request deduplication, and async translation/prefetch tasks
- `PDFService` for PDF document lifecycle, render metadata, hit-testing, and selection context extraction
- `VideoService` for subtitle lifecycle, offset state, subtitle lookup, and subtitle selection helpers
- Expanded `AnkiService` to own queue workflows and card-processing operations in addition to connection refresh
- GUI controllers: `MiningController`, `PDFController`, `VideoController`, and `WorkspaceController`
- Extracted helper widgets: `pdf_clickable_label.py`, `queue_dialog.py`, and `subtitle_generator_dialog.py`

Changed:
- `SelectionState` is now a signal-emitting core state manager instead of a passive dataclass container
- `main_window.py` now composes controllers/services and keeps compatibility wrappers only where tests and legacy entrypoints still depend on them
- Added direct coverage for the new seams with `test_translation_service.py`, `test_pdf_controller.py`, and `test_video_service.py`

Verification:
- Focused refactor test suite passed: `54 passed`

### 2026-05-11

#### Added Floating Shortcut Panel

Implemented a floating shortcut panel that overlays the right side of the main window in PDF and VIDEO modes. The panel provides quick access to:
- **Mark page complete** - Checkbox to track reading progress with completion state persisted to user data
- **Quick add to Anki** - Direct shortcut to add current selection without opening the edit dialog
- **View queue** - Quick access to pending cards dialog
- **Toggle dark mode** - Instant theme switching

The panel is minimizable to a small icon, repositions on window resize, and follows the 4-layer architecture with `CompletionTracker` state manager in the core layer and `ShortcutPanel` widget in the GUI layer. Page completion data is stored in `user_data.json` under a new `progress` section with timestamps, normalized file paths, and support for both PDF pages and video completion tracking.

#### Added Dark Mode And PDF Inversion

Added a persisted light/dark appearance setting in the gear menu, wired the GUI theme system to switch palettes at runtime, and refreshed the main LinguaLoop widgets in place when the mode changes. In PDF mode, dark appearance now inverts the rendered page image before highlights are painted so text-heavy PDFs display as dark background with light text.

#### Fixed Anki "Today" Counter

Added persisted per-day Anki add analytics for LinguaLoop-managed card additions and wired the command bar stats chip to use that state. The top-right counter now increments on successful direct adds and queued-card processing instead of always showing `0 today`.

#### Removed Embedded Console Pane

Removed the bottom-left `>_` console toggle and in-app console pane. LinguaLoop now sends runtime logs to the main Python terminal while keeping session log files on disk.

#### Compact PDF Header/Footer And Scroll Reset

Reduced the PDF-mode command bar and status bar heights, updated the footer guidance to include translate/phrase/Anki shortcuts, and reset the PDF scroll position to the top whenever the user changes pages.

#### Centralized Custom Scrollbar Styling

Added `Theme.get_scrollbar_style()` and applied the shared custom scrollbar styling to the welcome recent files list, PDF scroll area, queue list, and console output. This removes duplicated inline scrollbar CSS and makes scrollbar colors and hover states consistent with the app theme.

### 2026-05-09

#### Extended AGENTS.md with Comprehensive Quick-Start Guide

Extended AGENTS.md from 5 lines to 556 lines with a comprehensive quick-start guide for AI agents working on this codebase. The extension provides:
