# Changelog

## 2026-05-12

### Added Content Browser to Welcome Page

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

### Main Window Refactor Cutover

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

## 2026-05-11

### Added Floating Shortcut Panel

Implemented a floating shortcut panel that overlays the right side of the main window in PDF and VIDEO modes. The panel provides quick access to:
- **Mark page complete** - Checkbox to track reading progress with completion state persisted to user data
- **Quick add to Anki** - Direct shortcut to add current selection without opening the edit dialog
- **View queue** - Quick access to pending cards dialog
- **Toggle dark mode** - Instant theme switching

The panel is minimizable to a small icon, repositions on window resize, and follows the 4-layer architecture with `CompletionTracker` state manager in the core layer and `ShortcutPanel` widget in the GUI layer. Page completion data is stored in `user_data.json` under a new `progress` section with timestamps, normalized file paths, and support for both PDF pages and video completion tracking.

### Added Dark Mode And PDF Inversion

Added a persisted light/dark appearance setting in the gear menu, wired the GUI theme system to switch palettes at runtime, and refreshed the main LinguaLoop widgets in place when the mode changes. In PDF mode, dark appearance now inverts the rendered page image before highlights are painted so text-heavy PDFs display as dark background with light text.

### Fixed Anki "Today" Counter

Added persisted per-day Anki add analytics for LinguaLoop-managed card additions and wired the command bar stats chip to use that state. The top-right counter now increments on successful direct adds and queued-card processing instead of always showing `0 today`.

### Removed Embedded Console Pane

Removed the bottom-left `>_` console toggle and in-app console pane. LinguaLoop now sends runtime logs to the main Python terminal while keeping session log files on disk.

### Compact PDF Header/Footer And Scroll Reset

Reduced the PDF-mode command bar and status bar heights, updated the footer guidance to include translate/phrase/Anki shortcuts, and reset the PDF scroll position to the top whenever the user changes pages.

### Centralized Custom Scrollbar Styling

Added `Theme.get_scrollbar_style()` and applied the shared custom scrollbar styling to the welcome recent files list, PDF scroll area, queue list, and console output. This removes duplicated inline scrollbar CSS and makes scrollbar colors and hover states consistent with the app theme.

## 2026-05-09

### Extended AGENTS.md with Comprehensive Quick-Start Guide

Extended AGENTS.md from 5 lines to 556 lines with a comprehensive quick-start guide for AI agents working on this codebase. The extension provides:
