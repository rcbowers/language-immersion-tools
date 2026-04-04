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

Repo-tracked source code stays under `src/`.
Generated queue/session/log data goes under `data/`.
Legacy root data files are treated as import/fallback sources, not the preferred storage location.
