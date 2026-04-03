# Architecture

## Primary Product Shape

The repo is organized around one desktop app: `immersion_app`.

## Package Responsibilities

- `immersion_app.gui`: unified workspace shell, PDF/video views, reusable widgets
- `immersion_app.core`: queue persistence, session state, Anki helpers, language config
- `immersion_app.integrations`: translation and subtitle generation backends
- `immersion_app.media`: subtitle parsing and media filename matching

## Compatibility Layer

Legacy launchers remain in `apps/sentence_miner/` so older scripts still resolve, but new development should target `src/immersion_app/`.

## Runtime Data Policy

Repo-tracked source code stays under `src/`.
Generated queue/session/log data goes under `data/`.
Legacy root data files are treated as import/fallback sources, not the preferred storage location.
