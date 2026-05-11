# Changelog

## 2026-05-11

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
