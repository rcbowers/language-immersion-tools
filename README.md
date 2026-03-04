# Language Immersion Tools

A collection of Python tools designed to supercharge your language immersion workflow. Currently focused on Spanish, but adaptable to other languages.

## Tools Included

### 1. YouTube Subtitle Generator
Automatically generate accurate subtitles for YouTube videos using OpenAI's Whisper AI. Perfect for creating subtitles for content that doesn't have them, or for getting cleaner transcripts for sentence mining.

### 2. Spanish Sentence Miner (GUI)
Interactive PySide6 + PyMuPDF GUI for mining directly from PDFs. Click a word in the reader, auto-translate it, and create Anki cards immediately or via queue.

### 3. Spanish Sentence Miner (CLI)
Batch process pre-formatted sentences from a text file and automatically create Anki flashcards via the AnkiConnect API. Words are highlighted in the context sentence for easy recognition.

## Prerequisites

- Python 3.8 or higher
- FFmpeg (required for audio processing)
- Anki with AnkiConnect add-on (for sentence mining tool)

### Installing FFmpeg on Windows

Download from: https://www.gyan.dev/ffmpeg/builds/
Or use Chocolatey: `choco install ffmpeg`

### Installing AnkiConnect

1. Open Anki
2. Tools → Add-ons → Get Add-ons
3. Enter code: `2055492159`
4. Restart Anki

## Installation

```bash
pip install -r requirements.txt
```

**Note:** The first time you run the subtitle generator, Whisper will download the selected model (~100MB-3GB depending on size).

---

## YouTube Subtitle Generator

Generate Spanish (or other language) subtitles from YouTube videos.

### Basic Usage

```bash
# Default base model
python youtube_subtitle_generator.py "https://youtube.com/watch?v=VIDEO_ID"

# GPU-accelerated version (requires CUDA)
python youtube_subtitle_generator_gpu.py "URL"
```

### Model Options

```bash
# Tiny - fastest, least accurate (~75MB)
python youtube_subtitle_generator.py -m tiny "URL"

# Base - good balance (default, ~142MB)
python youtube_subtitle_generator.py -m base "URL"

# Small - better accuracy (~466MB)
python youtube_subtitle_generator.py -m small "URL"

# Medium - very accurate (~1.5GB)
python youtube_subtitle_generator.py -m medium "URL"

# Large - best accuracy (~3GB, requires good GPU)
python youtube_subtitle_generator.py -m large "URL"
```

### Additional Options

```bash
# Keep the audio file
python youtube_subtitle_generator.py --keep-audio "URL"

# Custom output directory
python youtube_subtitle_generator.py -o "my_subtitles" "URL"
```

### Model Size Recommendations

- **tiny/base**: Good for general Spanish shows, fast processing
- **small**: Better for shows with accents or background noise
- **medium**: Best quality without requiring a GPU
- **large**: Professional quality (slow without GPU)

### Output

- Creates `.srt` subtitle files (standard format, works with most video players)
- Files are saved in the `downloads/` folder (or custom directory)
- Can be used with VLC, YouTube uploads, or sentence mining tools

---

## Spanish Sentence Miner (GUI)

Interactive PDF reader for creating Anki flashcards with automatic translation powered by Google Translate.

### Features

- **PDF Click Mining**: Open a PDF and click words directly in-page
- **Automatic Translation**: Selected word is translated automatically
- **Context Capture**: Uses the clicked line as card context sentence
- **Quick Add + Queue**: Add immediately to Anki or stage in `words_to_process.txt`
- **Batch Queue Processing**: Process queued entries to Anki in one pass
- **Anki Integration**: Direct connection to Anki via AnkiConnect

### Setup

1. Make sure Anki is running
2. Install required dependencies:
   ```bash
   pip install PySide6 PyMuPDF googletrans==4.0.0-rc1
   ```
3. Edit `spanish_sentence_miner.py` configuration if needed:
   - `DECK_NAME`: Your target Anki deck (default: "2025 Spanish Immersion")
   - `MODEL_NAME`: Card type (default: "Basic")

### Usage

```bash
python sentence_miner_gui.py
```

### Workflow

1. **Open a PDF** in the GUI (`Ctrl+O`)
2. **Click a target word** in the page
   - The clicked word is highlighted
   - The word is translated automatically
   - Context line is captured for card front
3. **Choose card action**
   - `Add Now`: creates the card in Anki immediately
   - `Add to Queue`: appends sentence/word/translation to `words_to_process.txt`
4. **Click `Process Queue`** to batch submit all queued entries to Anki

### Card Format

- **Front**: Spanish sentence with target word highlighted in red
- **Back**: English translation of the target word
- **Tags**: `sentence-mining`, `auto-generated`

---

## Spanish Sentence Miner (CLI)

Command-line batch processing tool for creating Anki flashcards from pre-formatted text files.

### Setup

1. Make sure Anki is running
2. Edit the script configuration if needed:
   - `DECK_NAME`: Your target Anki deck (default: "2025 Spanish Immersion")
   - `MODEL_NAME`: Card type (default: "Basic")

### Input Format

Create a `words_to_process.txt` file with entries in this format:

```
Spanish sentence here
target_word
English translation here

Next Spanish sentence
next_word
Another translation

...
```

Each entry is 3 lines:
1. Spanish sentence containing the target word
2. The target word to highlight
3. English translation of the sentence

### Usage

```bash
python spanish_sentence_miner.py
```

The script will:
1. Test connection to Anki
2. Process all entries from `words_to_process.txt`
3. Create flashcards with the target word highlighted in red
4. Log successful entries to `processed_words.txt`
5. Remove successfully processed entries from `words_to_process.txt`

### Card Format

- **Front**: Spanish sentence with target word highlighted in red
- **Back**: English translation
- **Tags**: `sentence-mining`, `auto-generated`

### Error Handling

- If any entries fail, they remain in `words_to_process.txt` for retry
- Successful entries are logged to `processed_words.txt` with timestamps

---

## Workflow Suggestions

### For Comprehensible Input

1. Use the subtitle generator on Spanish YouTube content
2. Watch videos with generated subtitles
3. Extract interesting sentences for sentence mining
4. Use the sentence miner to create Anki cards

### For Sentence Mining with GUI

1. Generate subtitles for content at your level
2. Open a text-based `.pdf` with your target language content
3. Launch `sentence_miner_gui.py`
4. Click target words in the PDF - translations happen automatically
5. Click `Add Now` or `Add to Queue`, then `Process Queue` when ready

### For Batch Sentence Mining (CLI)

1. Generate subtitles for content at your level
2. Open the `.srt` file and find sentences with target vocabulary
3. Format them in `words_to_process.txt`
4. Run `spanish_sentence_miner.py` to batch-create flashcards

### For Testing Comprehension

1. Generate subtitles for native content
2. Watch without subtitles first
3. Re-watch with generated subtitles to check comprehension
4. Mine unknown words/phrases

---

## Troubleshooting

### Subtitle Generator

**"FFmpeg not found"**: Install FFmpeg and add it to your PATH

**Out of memory**: Use a smaller model (tiny or base)

**Slow processing**:
- Use smaller model
- GPU acceleration helps (requires CUDA for NVIDIA GPUs)
- A 20-minute video takes ~5-10 minutes on base model with CPU

### Sentence Miner

**"Failed to connect to AnkiConnect"**: Make sure Anki is running and AnkiConnect is installed

**"Deck not found"**: Check that your deck name matches the `DECK_NAME` setting

**"Model not found"**: Check that you're using a valid note type (like "Basic")

---

## Tips for Better Results

### Subtitles
- Whisper works best with clear audio
- Spanish (Spain vs Latin American) variants are handled automatically
- If subtitles have errors, try a larger model
- You can manually edit the `.srt` file to fix any mistakes

### Sentence Mining
- Use sentences at your comprehension level (i+1)
- Keep sentences concise and focused on the target word
- Review cards regularly for best retention
- You can edit cards in Anki after creation if needed

---

## Future Tool Ideas

- Audio extractor for creating listening practice files
- Vocabulary frequency analyzer for subtitle files
- Duplicate sentence detector for Anki decks
- Batch subtitle processor for entire YouTube playlists

---

## Contributing

This is a personal language learning toolkit. Feel free to fork and adapt for your own needs. If you create a new tool 
that you think would be useful for others, feel free to contact ryanbowers166@gmail.com to add it to the main repo.  

## License

MIT License - use these tools however helps your language learning journey!
