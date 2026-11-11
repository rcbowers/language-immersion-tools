<p align="center"><img src="img/logo.png" alt="LinguaLoop" width="420"></p>

# LinguaLoop

**Read and watch in the language you're learning, click any word you don't know, and turn it into an Anki card in one keystroke.**

LinguaLoop is a free desktop app for *active immersion*: open a PDF (a novel, a comic, an article) or a video with subtitles, click a word or phrase to see its translation in context, and send it to Anki together with the sentence it came from. It keeps track of the words you've already mined, highlights them as you read, and logs how much time you actually spend studying.

![Reading a Spanish PDF with a translation popover](docs/screenshots/reader.png)

## Features

- **PDF reader**: click a word to translate it, Shift+click to select a phrase, Ctrl+hover for quick lookups. Light and dark mode (pages are inverted in dark mode).
- **Video player with clickable subtitles**: load an `.srt` (or generate one with Whisper), click subtitle words while you watch, nudge subtitle timing with Ctrl+←/→.
- **One-keystroke Anki cards**: the sentence becomes the front with your word highlighted; the translation goes on the back. If Anki isn't running, cards are queued and sent later.
- **Known-word highlighting**: words already in your Anki deck are highlighted, so new vocabulary stands out.
- **Online or offline translation**: Google Translate (online) or MarianMT models running locally (optional install).
- **Study-time tracking**: an indicator in the status bar shows when time is being counted; the Activity view shows study time, streaks, pages read and video minutes watched.
- **Library and progress**: recently opened sources, resume where you left off, mark pages and episodes complete.

Supported languages: Spanish, French, Italian, Japanese, Chinese and English (any pair).

## Install

### Requirements

- **Anki** desktop with the **AnkiConnect** add-on: in Anki choose *Tools → Add-ons → Get Add-ons…* and enter code `2055492159`, then restart Anki.
- **Python 3.11 or newer** (3.12 recommended). A packaged Windows installer is planned. Until then, LinguaLoop runs from source.
- **FFmpeg** on your `PATH`, only if you want to generate subtitles or use the audio tools.

### From source

```bash
git clone https://github.com/ryanbowers166/language-immersion-tools.git
cd language-immersion-tools
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Optional extras:

```bash
pip install -r requirements-offline.txt   # offline translation (MarianMT + PyTorch, several GB)
pip install -r requirements-media.txt     # Whisper subtitle generation and the CLI tools
```

### Run

```bash
# Windows
run_lingualoop.bat
# any platform
python -m immersion_app.app        # with src/ on PYTHONPATH, e.g. PYTHONPATH=src
```

## First run

The welcome screen shows a **Getting started** checklist:

![Welcome screen](docs/screenshots/welcome.png)

1. **Connect Anki.** Open Anki (with AnkiConnect installed), then open **Settings** (Ctrl+,) → *Load from Anki* and pick the **deck** cards should go to, the **note type**, and which fields hold the **sentence** and the **translation**. The default is a deck called `LinguaLoop` using the built-in `Basic` note type (`Front` / `Back`). *Create deck* makes the deck if it doesn't exist yet.
2. **Choose your languages**: the language you're learning and the one to translate into.
3. **Open a PDF or video** with **Open PDF or video…** (Ctrl+O).

![Settings](docs/screenshots/settings.png)

## Everyday use

| Action | How |
| --- | --- |
| Translate a word | Click it (PDF or subtitle) |
| Translate a phrase | Click the first word, Shift+click the last |
| Quick lookup (PDF) | Hold Ctrl and hover |
| Add the selection to Anki | Ctrl+Space (or Ctrl+Enter, or the **+** in the popover) |
| Queue it for later | Ctrl+Shift+Enter |
| Open a PDF or video | Ctrl+O |
| Load subtitles for the video | Ctrl+L |
| Previous / next page (PDF) | ← / → |
| Play / pause, seek 5 s (video) | Space, ← / → |
| Shift subtitles ±0.5 s | Ctrl+← / Ctrl+→ |
| Zoom in / out / fit width (PDF) | Ctrl+= / Ctrl+- / Ctrl+0 |
| Subtitle size (video) | Ctrl+= / Ctrl+- |
| Fullscreen | F11 or F |
| Close the translation popover | Esc |
| Settings | Ctrl+, |

**Queue:** when Anki isn't reachable, cards are saved to a queue instead of being lost. Send them with **View Queue → Process Queue** once Anki is open.

**Study time:** the dot in the status bar is filled (●) while time is being counted. It counts while LinguaLoop is the active app and you've used the mouse or keyboard in the last 2 minutes (or a video is playing), and pauses otherwise. It picks up again as soon as you come back.

![Dark mode](docs/screenshots/reader_dark.png)

## Translation: online vs offline

- **Online** (default) uses Google Translate via the unofficial [`googletrans`](https://pypi.org/project/googletrans/) library. It needs an internet connection and sends the words you look up to Google. Because it's unofficial it can occasionally break or be rate-limited. If you hit that, turn off *Pre-translate words on each page* in Settings, or switch to offline.
- **Offline** uses [MarianMT](https://huggingface.co/Helsinki-NLP) models via Hugging Face Transformers. Install `requirements-offline.txt`. The model for each language pair downloads the first time you use it (a few hundred MB), and after that nothing leaves your computer.

Switch between them in Settings, or click the *Translation* badge in the status bar.

## Where your data lives

LinguaLoop keeps its settings, card queue, study history and logs in a per-user folder:

- Windows: `%APPDATA%\LinguaLoop`
- macOS: `~/Library/Application Support/LinguaLoop`
- Linux: `~/.local/share/LinguaLoop`

*Settings → Data folder → Open* takes you there. Set the `LINGUALOOP_DATA_DIR` environment variable to use a different folder (e.g. a synced or portable one). If you used an older version that stored data in the repo's `data/` folder, it's copied over automatically the first time you start this version.

## Companion tools

Command-line helpers live in `src/immersion_app/cli` (run with `src` on `PYTHONPATH`):

```bash
python -m immersion_app.cli.queue                                    # send queued cards to Anki
python -m immersion_app.cli.subtitles --mode folder --video-folder videos -l es   # Whisper subtitles for a folder
python -m immersion_app.cli.audio "https://youtube.com/watch?v=..."  # download/extract audio
python -m immersion_app.cli.analyze books --types srt pdf            # word-frequency analysis
```

**`auto_miner.py`** is an interactive terminal miner for batches of words. List words under `# <source>` headers (a PDF/SRT path or a web URL) in a markdown file. It finds each word in its source, lets you choose the example sentence and adjust the context, and creates the cards.

```bash
python auto_miner.py [INPUT_FILE] [--deck "My Deck"] [--source-lang es] [--target-lang en]
```

The default input file is `automine_inputs.md` in the data folder. Point it elsewhere with the `LINGUALOOP_AUTOMINE_FILE` environment variable (handy for keeping the list in a notes app). The terminal UI currently needs Windows.

`scripts/` has a few extra utilities (vocabulary counter, AV1→H.264 video converter).

## Troubleshooting

- **"Anki: Not connected"**: make sure Anki is open and AnkiConnect is installed (code `2055492159`). Click the badge to re-check. If Anki is running but the deck or note type doesn't exist, the checklist and Settings tell you what's missing.
- **Translations fail or say "rate limited" (HTTP 429)**: Google is throttling the unofficial API. Turn off pre-translation in Settings, wait a while, or use offline translation.
- **Video won't play**: LinguaLoop uses Qt's FFmpeg backend. Some AV1/HEVC files need converting. `scripts/convert_to_h264.ps1` does this on Windows.
- **Logs**: in the data folder under `logs/`, one file per session.

## Contributing

Bug reports and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, tests and the architecture overview.

## License

LinguaLoop is free software under the [GNU General Public License v3.0](LICENSE).

It builds on [PySide6/Qt](https://www.qt.io/qt-for-python) (LGPL-3.0), [PyMuPDF](https://pymupdf.readthedocs.io/) (AGPL-3.0), [googletrans](https://pypi.org/project/googletrans/) (MIT), and optionally [Transformers](https://github.com/huggingface/transformers)/[PyTorch](https://pytorch.org/) and [Whisper](https://github.com/openai/whisper). It bundles the [Inter](https://rsms.me/inter/) typeface (SIL Open Font License 1.1, see `src/immersion_app/gui/fonts/OFL.txt`). LinguaLoop is not affiliated with Anki or AnkiConnect.

Only use LinguaLoop with content you have the right to use. The repository ships no books or videos.
