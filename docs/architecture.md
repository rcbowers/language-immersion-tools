# Architecture

## Primary Product Shape

The repo is organized around one desktop app: `immersion_app`.

## Package Responsibilities

- `immersion_app.gui`: unified workspace shell, PDF/video views, reusable widgets
- `immersion_app.cli`: supported command-line entrypoints for queue processing, subtitles, audio, and analysis
- `immersion_app.core`: queue persistence, session state, Anki helpers, language config
- `immersion_app.integrations`: translation and subtitle generation backends
- `immersion_app.media`: subtitle parsing and media filename matching

## Runtime Data Policy

Repo-tracked source code stays under `src/`. Nothing is written inside the source tree or install folder at runtime.

Generated state (user data, card queue, logs, Anki vocabulary snapshot, previews) lives in the per-user data folder from `immersion_app.core.paths.DATA_ROOT`: `%APPDATA%\Language Immersion Tools` on Windows, `~/Library/Application Support/LanguageImmersionTools` on macOS, `~/.local/share/LanguageImmersionTools` on Linux. The `IMMERSION_DATA_DIR` environment variable overrides it (the test suite uses this).

A pre-1.0 `<repo>/data` folder is copied into the new location once (`paths.migrate_legacy_data`, called from `app.main`) and left in place. Legacy root files (`words_to_process.txt`, `sentence_miner_user_data.json`) are still read as fallback import sources.

## Settings

User-configurable Anki settings (deck, note type, field mapping, tags, AnkiConnect URL) live in `user_data["anki"]`. They're loaded into `core.anki.AnkiSettings` and applied with `configure_anki()` at startup and whenever the Settings dialog is saved (`gui/controllers/settings_controller.py`). The CLIs (`cli/queue.py`, `auto_miner.py`) read the same settings.

## Study-time tracking

See [usage-time-tracking.md](usage-time-tracking.md).
