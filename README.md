![logo.png](img%2Flogo.png)

# LinguaLoop Workspace

This repo now centers on one desktop application: a unified immersion workspace for mining vocabulary from PDFs and videos. Subtitle generation and queue processing remain available, but they support the main app instead of living as separate first-class products.

## What Changed

- One main GUI entrypoint instead of separate PDF/video launch flows
- A real package layout under `src/immersion_app/`
- Runtime data moved under `data/` instead of the repo root
- Structured queued-card storage with legacy import fallback
- Compatibility wrappers kept under `apps/sentence_miner/`

## Repo Layout

```text
src/immersion_app/
  app.py                  # main GUI entrypoint
  gui/                    # unified workspace window and widgets
  core/                   # queue, session, Anki, language config
  integrations/           # translation and subtitle generation
  media/                  # PDF/SRT matching and parsing helpers

apps/sentence_miner/      # compatibility launchers/wrappers
data/                     # runtime queue, logs, and session state
docs/                     # screenshots and notes
```

## Main App

Launch the unified workspace with:

```bat
run_sentence_miner_gui.bat
```

Or directly:

```bash
set PYTHONPATH=src
python -m immersion_app.app
```

The app workflow is:

1. Open a PDF or video.
2. Select a word or phrase.
3. Review or edit the translation.
4. Add to Anki immediately or queue it for later.

## Queue and Runtime Data

- Structured queue: `data/queue/queued_cards.json`
- Processed log: `data/logs/processed_cards.log`
- User/session state: `data/state/sentence_miner_user_data.json`

If legacy root files such as `words_to_process.txt` or `sentence_miner_user_data.json` exist, the new app will fall back to them when needed.

## Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Run a quick syntax check:

```bash
python -m py_compile src/immersion_app/app.py src/immersion_app/gui/main_window.py
```

Run the queue processor compatibility CLI:

```bash
python apps/sentence_miner/spanish_sentence_miner.py
```

## Requirements

- Python
- PySide6
- PyMuPDF
- FFmpeg for subtitle/media workflows
- Anki with AnkiConnect for card creation

## Notes

- The unified workspace currently instantiates correctly in the project venv.
- In this environment, Qt multimedia backends were unavailable in headless verification, so video playback was only smoke-tested up to window initialization.
