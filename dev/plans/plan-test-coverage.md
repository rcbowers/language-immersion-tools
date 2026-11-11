# Plan: Test Coverage for Intended Behavior

Status: proposed · Created: 2026-11-11

Goal: cover the behavior the README, `docs/architecture.md` and the public-release plan say the app has, with the most effort on places where a bug loses user data or silently breaks mining. Line coverage is a guide, not the target.

## 1. Where we are

Measured with `coverage` over `tests/` (254 tests, all pass, about 35-55 s). **7,699 statements, 48% covered.** `coverage` is not in `requirements-dev.txt`; I ran it from a temp folder, so nothing in the venv changed.

| Area | Coverage | Notes |
| --- | --- | --- |
| Pure state/trackers (`usage_time_tracker`, `completion_tracker`, `selection_state`, `mode`, `activity_analytics`, `auto_mining`, `automine_queue`, `settings_dialog`) | 89-100% | Healthy. Leave alone. |
| `pdf_service`, `pdf_controller`, `mining_controller`, `subtitle_widget`, `subtitle_parser`, `source_context` | 68-79% | Mostly good; gaps are error paths. |
| `anki_service` 49%, `anki.py` 39%, `translation_service` 56%, `translation_backends` 21% | | **The core mining path. Biggest risk.** |
| `queue_store` 15%, `recent_files` 32%, `anki_snapshot` 29% | | Small, pure, persist user data. Cheap to fix. |
| `video_controller` 31%, `workspace_controller` 16%, `settings_controller` 50%, `analytics_controller` 30% | | Orchestration with real logic (restore position, session restore). |
| `main_window.py` | 17% (1,030 of 1,248 statements untested) | Known problem file; see §4. |
| `cli/*`, `app.py`, `subtitle_generation`, several widgets | 0-25% | Mostly lower risk; see §5. |

`auto_miner.py` is covered by `tests/test_auto_miner_cli.py` but my run did not import it from the measured path, so it shows no number. Add it to the coverage config (§6).

Structural gaps beyond the numbers:

- `AGENTS.md` expects `tests/core/` and `tests/gui/`. About half the tests are still flat in `tests/`.
- Two logging test files (`test_logging.py`, `test_logging_simple.py`) overlap `test_logging_config.py`; worth a look when tidying.
- Many tests use `unittest.TestCase` with a fake pool. Keep that style for services (matches the exemplar `test_mode_manager.py`).

## 2. Priority 1: protects user data and the mining flow

Each item names the intended behavior and the test that would catch its breakage.

### 2a. `core/anki.py` (39%), mock `urllib.request.urlopen` / `anki_connect_invoke`

- `anki_connect_invoke`: URLError/timeout → `ConnectionError`; bad JSON → `RuntimeError`; response without both `error` and `result` → `RuntimeError`; non-null `error` → `RuntimeError("AnkiConnect error: …")`; uses the configured URL and the 10 s timeout, and the 60 s one for bulk calls.
- `check_anki_setup`: connected + all present → `ok`; missing deck, missing note type, missing fields each give the right message; connection failure → `connected=False` and does **not** raise; failure on `modelFieldNames` doesn't crash.
- `AnkiSettings.from_dict` / `to_dict` round trip, tag parsing from a string and from a list (some of this is in `test_settings.py`; extend to blank strings and non-dict input).
- `add_anki_card`: builds the note with configured deck, note type, field names and tags; the sentence has the target word wrapped as a red `[word]` span; HTML in the sentence is escaped; word match is case-insensitive; regex characters in the word (e.g. `a.b`, `(x)`) don't break it.
- `fetch_deck_words`: parses the red-span form, the bare `[word]` form, nested tags, and ignores notes with neither; returns lowercase; empty deck returns an empty set without calling `notesInfo`; honors a custom sentence field.
- `load_anki_options`: one failing note type yields `[]` fields, not an exception.
- `_find_anki_executable`: `ANKI_PATH` wins over defaults (monkeypatch env and `os.path.isfile`). The `start_anki_if_needed` error cases: no executable → `FileNotFoundError`; `Popen` OSError → `RuntimeError`; never available → `ConnectionError` (patch `time.monotonic`/`sleep`).

### 2b. `core/anki_service.py` (49%), async add and queue processing

Intended: cards are never silently lost; duplicate-note errors reach the UI; the queue is rewritten with only the failed entries.

- `AnkiAddTask`: success emits `finished` with `note_id`; `RuntimeError` ("duplicate") emits `failed` with `is_connection_error=False`; `ConnectionError` emits it with `True`.
- `AnkiService._on_add_failed`: connection error flips `is_connected` to False; both `card_add_failed` and `card_failed` fire.
- `QueueProcessTask`: second and later cards with the same sentence get ` (2)`, ` (3)` suffixes; per-entry failures land in `failed_entries` and the rest still run.
- `_finalize_queue_processing`: appends to the processed log only when something succeeded; saves **only failed entries** back to the queue; emits both signals; the count and path in `queue_processed` are right.
- `process_queue_now` returns the same split as the async path.
- `_on_status_finished`: sets `setup_status` (and the fallback when `status` is `None`); only emits `vocabulary_loaded` when words are not `None`. `_on_status_failed` marks disconnected and emits `setup_status_changed`.
- `queue_card` persists then emits `queue_entry_added`; `build_queue_payload` uses the word when the sentence is empty.

### 2c. `core/queue_store.py` (15%, `anki_snapshot` 29%), use the `LINGUALOOP_DATA_DIR` temp folder from `conftest.py`

- Save then load round trip with non-ASCII text (Japanese, accents).
- Atomic save: no `.tmp` left behind; the old file survives if the write raises (patch `write_text`).
- Corrupt JSON, or JSON that is a dict rather than a list, falls back to the legacy file; non-dict list entries are dropped.
- Legacy three-line format: parses sentence/word/translation triples, skips blank lines, ignores a trailing partial group, marks `source_name="legacy-import"`.
- `append_queue_entry` / `queue_count`; `append_processed_log` writes the expected lines and also writes the legacy log only if it exists.
- `anki_snapshot`: save/load round trip, missing file → empty set, corrupt file → empty set, **words from a different deck are ignored** (README/plan §2 promise).

### 2d. `core/translation_service.py` (56%), fake backends, fake pool

- Language change (`set_languages`) clears the cache and bumps the context version, so a late result from the old language pair is **dropped** (never cached, never emitted).
- A visible request for text already being prefetched upgrades it to visible and returns the same request id.
- Failure paths: `translation_failed` carries the visible flag; stale failure ignored; failed request id is freed so a retry actually runs.
- `prefetch_async`: disabled → no work; online mode uses single tasks on the prefetch pool (max 2 threads); offline uses one batch task; skips cached and in-flight text.
- Batch: count mismatch emits `batch_failed` and caches nothing; a batch failure retries each text individually as non-visible.
- `TranslateTask` / `BatchTranslateTask` directly: fall back to per-text `translate` when the backend has no `translate_batch`.
- `AvailabilityTask`: a probe that raises becomes `False` for that mode, the other mode is still reported; `check_availability_async` updates `availability` and emits `availability_changed`.
- `probe_mode_available("offline")`: false when any of transformers/torch/sentencepiece is missing (patch `importlib.util.find_spec`); never imports torch.
- `shutdown()` disables prefetch and clears the pool.
- `_get_translation_language_codes` uses Marian codes offline and Google codes online.

### 2e. `integrations/translation_backends.py` (21%), mock the libraries, no network

- `OnlineTranslationBackend.translate`: empty text returns empty; the result object's text is extracted for both sync and async googletrans variants; HTTP 429/errors propagate as exceptions instead of returning the source text (that behavior is why `test_translation_backends.py` exists, extend it); translator is reset after a failure.
- `translate_batch`: result order and count preserved.
- `MarianMTTranslationBackend`: model name per language pair; unknown pair raises a clear error; model cache reuse and `clear_model_cache`; device selection (patch `torch.cuda.is_available`). Skip these with `pytest.importorskip("torch")` so CI without the offline extras stays green.

### 2f. `core/recent_files.py` (32%), pure functions

- Adding the same path again (different case on Windows, relative vs absolute) moves it to the top rather than duplicating.
- List capped at `MAX_RECENT_FILES` (5); newest first.
- PDF entries store `page_index`, video entries store `video_position_ms`; missing keys default to 0.
- `get_recent_files(validate_exists=True)` hides deleted files but doesn't mutate the stored list.
- `remove_recent_file`; `format_time_ago` at each boundary (59 s, 60 s, 1 h, 1 d, 1 wk, ~1 mo), singular vs plural, bad input → "Unknown" (patch `datetime`, don't sleep); `format_position_metadata` shows "Page N" (1-based) and `H:MM:SS` vs `M:SS`.

## 3. Priority 2: orchestration that restores state

### 3a. `workspace_controller` (16%), fake window + fake controllers

- `on_recent_file_selected` routes pdf vs video and passes the saved position; a file that no longer exists is removed from recent files and the user is told, not crashed.
- `restore_last_session`: tries the last video, then PDF; failure of one falls through; nothing saved → welcome screen.
- `close_current_file` saves position first, resets mode to WELCOME, and clears selection/subtitles.

### 3b. `video_controller` (31%), extend `tests/gui/test_video_controller.py`

- `on_position_changed`: highlights the right subtitle at boundaries (start inclusive, end exclusive), none in gaps, handles an empty subtitle list.
- `_save_position_periodically` writes `video_position_ms` to recent-file data and not when no video is loaded.
- `load_subtitles` bad or empty SRT shows an error and leaves the player usable; `replay_subtitle`, `toggle_play_pause` state.
- Subtitle offset shift (±0.5 s) changes which line is active.

### 3c. `settings_controller` (50%) and `analytics_controller` (30%)

- `apply` persists languages, translation mode, prefetch, appearance and the Anki block to `user_data` and calls `configure_anki`; changing only languages clears the translation cache.
- `_on_options_loaded` / `_on_options_failed` update the right dialog; a closed dialog is ignored; `AnkiOptionsTask` with `create_deck_name` creates the deck before listing.
- Analytics controller: dialog refreshes when visible and does nothing when hidden.

### 3d. Smaller core pieces

- `core/shortcuts.py` (48%): `update_for_mode` enables only the group for the current mode (WELCOME/PDF/VIDEO).
- `core/signals.safe_emit`: swallows `RuntimeError` from a deleted receiver only; other errors propagate.
- `core/main_thread_monitor.py` (33%): reports a stall over the threshold and not under it (inject the clock).
- `core/logging_config.py` (64%): file handler rotation settings, idempotent setup.
- `core/video_service.py`, `pdf_service.py`: remaining 10-23 statements, mostly error paths (corrupt PDF, missing file).
- `media/subtitle_parser.py` (76%): multi-line cues, BOM, CRLF, malformed timestamps, overlapping cues, comma vs dot milliseconds, non-UTF-8 fallback.
- `core/user_data.py` (85%): corrupt file is backed up and replaced by defaults rather than crashing; flush on exit actually writes (plan §3 data-loss items).

## 4. Priority 3: `main_window.py` (17%)

`AGENTS.md` says not to add features here and to extract first. The same holds for tests: don't write large pytest-qt tests against the 1,892-line window. Instead:

1. Add a **smoke test** (`tests/gui/test_main_window_smoke.py`): construct `MainWindow` with a throwaway data dir and offscreen Qt, a fake Anki service and a fake translation backend; assert it shows, starts in WELCOME, and closes cleanly with `closeEvent` flushing user data. This one test covers most of the construction code and guards the 20 remaining `hasattr` creation-order guards.
2. Add **flow tests through controllers** for the flows the README promises, with the window as a thin fake (pattern already used in `test_mining_controller.py`):
   - click word → translation shown → Ctrl+Space adds a card (Anki up) / queues it (Anki down);
   - open a PDF, close it, reopen from Recent at the saved page;
   - switch translation mode in Settings → availability re-check, fall back when unavailable.
3. As logic moves out of the window during the ongoing break-up, require tests for the extracted piece in the same change (already in `AGENTS.md`).

## 5. Priority 4: lower risk, do opportunistically

- Widgets via pytest-qt signal tests: `transport_bar` (20%), `translation_popover`, `card_feedback_toast`, `getting_started_panel` (state-per-status text/buttons), `shortcut_panel`, `queue_dialog`, `recent_files_menu`, `welcome_recent_files`, `chapter_rail`, `activity_analytics_dialog`. Test the signals they emit and the text they show for a given state; skip pixel layout.
- `cli/queue.py` (sends queued cards, prints counts) is worth a small test with a fake service. `cli/analyze.py` pure helpers (`clean_spanish_text`, `normalize_accents`, `parse_srt_file`, `filter_stopwords`) are easy; the spaCy and matplotlib parts can be skipped. `cli/subtitles.py`, `cli/audio.py`, `integrations/subtitle_generation.py` depend on Whisper/ffmpeg/yt-dlp: test argument parsing and command construction only, with subprocess mocked.
- `app.py`: one test that `main()` wires logging, data migration and the window (all patched).

## 6. Process changes

1. Add `pytest-cov` to `requirements-dev.txt` and a `[coverage:run]` section (`source = src/immersion_app, auto_miner`; `omit` the `cli/` heavy modules if we decide to). Print the report in CI with no failure threshold at first.
2. Once Priority 1 lands, set a floor per area rather than one global number: `core/` ≥ 85%, `integrations/` ≥ 70%, `gui/controllers/` ≥ 75%. Ratchet up; don't gate on `main_window.py`.
3. Move flat `tests/test_*.py` into `tests/core/`, `tests/gui/`, `tests/integrations/`, `tests/media/` as the matching file is touched (don't do a repo-wide move in the same PR as new tests).
4. Put shared fakes (`_Pool`, fake window, fake Anki service, `urlopen` stub that returns canned AnkiConnect JSON) in `tests/conftest.py` or `tests/fakes.py`; they're currently copy-pasted per file.
5. All tests stay offline and free of real Anki, real Google and real model downloads. `conftest.py` already isolates the data dir; add an autouse guard that fails any test that opens a real socket.

## 7. Suggested order and size

| Step | Scope | Est. new tests |
| --- | --- | --- |
| 1 | §2c `queue_store`, `anki_snapshot`, §2f `recent_files` (pure, fast) | ~25 |
| 2 | §2a `anki.py`, §2b `anki_service` | ~35 |
| 3 | §2d `translation_service`, §2e backends | ~30 |
| 4 | §3 controllers and small core pieces | ~30 |
| 5 | §4 `main_window` smoke and flow tests | ~8 |
| 6 | §6 tooling (pytest-cov, CI report, shared fakes) | n/a |
| 7 | §5 widgets and CLI, as time allows | ~25 |

Steps 1-3 should take overall coverage from 48% to roughly 60-65% and put the mining path above 85%.

## 8. Open questions

- Is CI allowed to fail under a coverage floor, or should it only report?
- Should the offline-translation (torch) tests run in CI, or stay local-only behind `importorskip`?
- Are `cli/analyze.py`, `cli/audio.py` and `cli/subtitles.py` staying in the app, or moving out (they pull in spaCy, Whisper and yt-dlp)? That decides whether they need tests at all.
