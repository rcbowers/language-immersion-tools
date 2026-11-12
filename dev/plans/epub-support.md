# Plan: EPUB support in the reader (alongside PDF)

## Context
The app's reader is PDF-only. README already advertises "PDF/EPUB reader", but no EPUB code exists. PyMuPDF (already a dependency, >=1.24) opens EPUB natively and returns the same `get_text("words")` tuples, so the existing render -> click -> word -> translate pipeline works unchanged. No new dependency is needed. The new work is (a) reflow handling, (b) stable position persistence, and (c) fixing the places where the type "pdf" is hard-coded.

## Design decisions
1. **Keep `WorkspaceMode.PDF` as the single "document" mode.** Do not add `WorkspaceMode.EPUB`. That avoids a new stack page, shortcut group and `mode_string` branch. Distinguish the kind with a `file_type` of `"pdf"` or `"epub"` carried by `PDFService` (`doc_kind` property, derived from the file suffix). `ModeManager.mode_string()` still returns `"pdf"`; the Anki `source_type` should use the doc kind.
2. **Reflow:** after loading an EPUB, call `doc.layout(width, height, fontsize)` from `PDFService.load_document`, using a fixed page size (default 600x800 pt, user-tunable later). Everything downstream sees ordinary pages.
3. **Stable positions:** page indexes change when layout parameters change. For EPUB, persist `{"page_index", "chapter", "bookmark"}` where `bookmark` is `doc.make_bookmark(location)`, and restore with `doc.find_bookmark`. Keep `page_index` as a fallback for PDF and for old data.
4. **Completion tracking** (`completion_tracker`) stays page-index based. Keep layout parameters fixed so page indexes are stable. Note this limitation in the CHANGELOG rather than solving it now.

## Steps (per AGENTS.md: service first, tests with each step)
1. **`core/pdf_service.py`**
   - Add `doc_kind` and `is_reflowable`.
   - Layout on load for reflowable docs.
   - Add `get_toc()` passthrough and `bookmark_for_page` / `page_for_bookmark`.
   - Switch to `import pymupdf` to avoid the `fitz` deprecation warning. Update `preview_generator.py` too, and its test patch target.
2. **`core/recent_files.py`, `user_data.py`**
   - Make `add_recent_file` and `format_position_metadata` handle `"epub"` as a page type, so it no longer falls into the video branch.
   - Add the `bookmark` metadata key.
   - Add `doc_kind` to `last_session`, and bump the data `version` only if migration is needed (old sessions default to pdf).
3. **`gui/main_window.py` (minimal edits only; it is the problem file)**
   - Add `*.epub` to `SUPPORTED_CONTENT_FILTER`.
   - Update the welcome text and button label to "Open PDF, EPUB or video…" (`getting_started_panel.py` too).
   - Route `_on_browser_content_selected` for `"epub"`.
4. **`gui/controllers/workspace_controller.py`**
   - Suffix dispatch: `.pdf` and `.epub` go to the PDF controller.
   - `on_recent_file_selected` and `restore_last_session` accept `"epub"` and restore via the bookmark.
5. **`gui/controllers/pdf_controller.py`**
   - Pass the doc kind into `add_recent_file` and `content_browser_manager.add_content`.
   - Save the bookmark in `_persist_session` and on page navigation.
   - `fit_width` still works. Text pages are fixed-size, so fit-width just scales.
6. **Content browser and previews**
   - `preview_generator._generate_preview`: add an `"epub"` branch that renders page 0 (reuse `_generate_pdf_preview`).
   - `content_browser_item._format_metadata`: show "N pages" for epub. Update the grid empty-state text.
   - Recent-files icons (`welcome_recent_files.py`, `recent_files_menu.py`): add an epub icon and use `format_position_metadata`.
7. **Usage tracker and analytics**
   - `usage_time_tracker.on_document_loaded`: use `pdf_service.doc_kind` instead of the hard-coded `"pdf"`. Treat epub like pdf for page metrics.
   - `activity_analytics`: count epub in the PDF/document bucket (relabel "Documents" in the dialog) rather than adding a third mode_split entry.
8. **Chapters (optional but cheap):** wire the existing unused `ChapterRail` to `get_toc()` for EPUB (and PDF). If this is too invasive for `main_window.py`, defer it and list it as follow-up.
9. **Sentence context:** the click "sentence" is currently one text line. For EPUB, reuse `_sentences` from `media/source_context.py` on the page text, falling back to the line, so EPUB contexts are real sentences.
10. **`media/source_context.py` + `auto_miner.py`:** add `extract_epub_contexts` (PyMuPDF, per-chapter/page), and the `.epub` dispatch in `load_source_contexts`. Update the error text "Use a .pdf, .epub or .srt file". `cli/analyze.py` (pypdf) is out of scope.
11. **Docs:** CHANGELOG `[Unreleased]` -> `### Added` (EPUB reading; page numbers are layout-dependent), README caption, `docs/architecture_design_readme.md` line ~109, and AGENTS.md (also fix the stale "PDFService doesn't exist" section).

## Tests
- `tests/core/test_pdf_service_epub.py`: build a synthetic EPUB in `tmp_path` with `zipfile` (mimetype, container.xml, OPF, 2 XHTML chapters). Cover load, `is_reflowable`, word extraction, TOC, bookmark round-trip across a relayout.
- Extend `tests/gui/test_pdf_controller_navigation.py` with an EPUB fixture: load, navigation, restore from bookmark.
- `tests/core/test_recent_files` (add if missing): epub metadata and formatting.
- `tests/core/test_preview_generator.py`: epub branch.
- `tests/test_source_context.py`: PDF and EPUB extraction (this closes an existing gap).
- Usage tracker: epub session records page metrics.

## Verification
- `pytest -q` (Windows, offscreen Qt) is green and `pyflakes` is clean.
- Manual run: open a real EPUB (Spanish book), then click a word (popover translation, highlight), Shift+click a phrase, navigate pages, zoom and fit-width, dark mode. Mine a card and check the Anki payload `source_type`/location. Quit and reopen: recent files and last-session restore land on the same position. Check the content-browser thumbnail.
- `python auto_miner.py` against an `.epub` path yields contexts.

## Risks / open items
- Page numbers shift if layout parameters change, which affects completion tracking. This is mitigated by fixed layout parameters.
- DRM-protected or very image-heavy EPUBs may render poorly or fail. Show the existing load-error dialog.
- Reading-width and font-size user settings for EPUB are deferred.
