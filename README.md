![logo.png](img%2Flogo.png)

# LinguaLoop Workspace

This repo centers on one desktop application and a small set of package-based CLI tools under `src/immersion_app`.

## Repo Layout

```text
src/immersion_app/
  app.py                  # main GUI entrypoint
  cli/                    # package-based companion CLIs
  gui/                    # unified workspace window and widgets
  core/                   # queue, session, Anki, config
  integrations/           # translation and subtitle generation
  media/                  # subtitle/media parsing and matching

tests/                    # current automated tests
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

Workflow:

1. Open a PDF or video.
2. Select a word or phrase.
3. Review or edit the translation.
4. Add to Anki immediately or queue it for later.

## CLI Tools

All supported command-line tools now live under `src/immersion_app/cli`:

```bash
set PYTHONPATH=src
python -m immersion_app.cli.queue
python -m immersion_app.cli.subtitles --mode folder --video-folder "immersion materials"
python -m immersion_app.cli.audio "downloads\\video.mp4"
python -m immersion_app.cli.analyze downloads --types srt
```

## Queue and Runtime Data

- Structured queue: `data/queue/queued_cards.json`
- Processed log: `data/logs/processed_cards.log`
- User/session state: `data/state/sentence_miner_user_data.json`

Legacy root files such as `words_to_process.txt` and `sentence_miner_user_data.json` are treated as fallback import sources, not the preferred runtime format.

## Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Run syntax checks:

```bash
python -m py_compile src/immersion_app/app.py src/immersion_app/gui/main_window.py
```

Run tests:

```bash
set PYTHONPATH=src
python -m pytest tests -q
```

## Requirements

- Python
- PySide6
- PyMuPDF
- FFmpeg for subtitle/media workflows
- Anki with AnkiConnect for card creation

## Notes

- The unified workspace instantiates correctly in the project venv.
- In this environment, Qt multimedia backends were unavailable in headless verification, so video playback was only smoke-tested up to window initialization.
