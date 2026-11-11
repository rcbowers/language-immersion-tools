# Contributing to LinguaLoop

Thanks for helping. Bug reports, feature ideas and pull requests are all welcome.

## Reporting bugs

Open an issue using the *Bug report* template. Please include:

- what you did, what you expected, and what happened
- your OS, Python version and LinguaLoop version/commit
- the relevant log file: *Settings → Data folder → Open*, then look in `logs/`

Please don't attach copyrighted books or videos. A short description of the file (format, language) is enough.

## Development setup

```bash
git clone https://github.com/ryanbowers166/language-immersion-tools.git
cd language-immersion-tools
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -r requirements-dev.txt
```

Run the app from source with `python -m immersion_app.app` and `src` on `PYTHONPATH` (or `run_lingualoop.bat` on Windows).

To keep your real data out of the way while developing, point the app at a scratch folder:

```bash
set LINGUALOOP_DATA_DIR=%TEMP%\lingualoop-dev        # Windows (cmd)
export LINGUALOOP_DATA_DIR=/tmp/lingualoop-dev       # macOS / Linux
```

## Tests

```bash
python -m pytest
```

The suite runs headless (Qt's `offscreen` platform) and uses a throwaway data folder, both set up in `tests/conftest.py`. It doesn't need Anki, a network connection or the optional offline/Whisper extras. CI runs it on Windows and Linux for every push and pull request (`.github/workflows/tests.yml`).

- New code needs tests. Core state managers and services get plain unit tests. Widgets get signal and presentation tests via `pytest-qt` (`qtbot`). Controllers get tests with fake services.
- Don't depend on the real date, the network, or files outside `tmp_path`. Inject a clock or patch where needed (see `AnkiAnalyticsManager(today=...)`).

## Architecture in one minute

```
src/immersion_app/
  core/          state managers and services: no Qt widgets (QObject/Signal only)
  gui/           main window, controllers (orchestration) and widgets (presentation)
  integrations/  external systems: translation backends, Whisper
  media/         subtitle/PDF parsing and matching
  cli/           command-line tools
```

- State lives in `core/` managers that emit signals, and widgets display it. Widgets don't own business state or call services directly.
- Anything that touches the network, Anki or large files runs in a `QRunnable` worker and reports back with signals. Never block the UI thread. Use `core.signals.safe_emit` when emitting from a worker.
- All colours, fonts and sizes come from `gui/theme.py` (`Theme.*`). Don't hard-code styles.
- `gui/main_window.py` is still being decomposed. Put new logic in a service or controller, not in the window.

The full rules are in [`docs/architecture_design_readme.md`](docs/architecture_design_readme.md). [`AGENTS.md`](AGENTS.md) is a condensed version written for AI coding assistants, and it's a useful checklist for humans too.

## Pull requests

1. Branch from `master`.
2. Keep the change focused, and add or adjust tests.
3. Run `python -m pytest` and make sure it passes.
4. Add a line under *Unreleased* in [`CHANGELOG.md`](CHANGELOG.md) for anything a user would notice.
5. Describe what changed and why, plus how you tested it in the app.

By contributing you agree that your contributions are licensed under the project's [GPL-3.0 license](LICENSE).
