# YouTube Spanish Subtitle Generator

Automatically generate Spanish subtitles for YouTube videos using OpenAI's Whisper AI.

## Prerequisites

- Python 3.8 or higher
- FFmpeg (required for audio processing)

### Installing FFmpeg on Windows

Download from: https://www.gyan.dev/ffmpeg/builds/
Or use Chocolatey: `choco install ffmpeg`

## Installation

```bash
pip install -r requirements.txt
```

**Note:** The first time you run the script, Whisper will download the selected model (~100MB-3GB depending on size).

## Usage

### Basic usage (default base model):
```bash
python youtube_subtitle_generator.py "https://youtube.com/watch?v=VIDEO_ID"
```

### Using different model sizes:
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

### Keep the audio file:
```bash
python youtube_subtitle_generator.py --keep-audio "URL"
```

### Custom output directory:
```bash
python youtube_subtitle_generator.py -o "my_subtitles" "URL"
```

## Model Size Recommendations

- **tiny/base**: Good for general Spanish shows, fast processing
- **small**: Better for shows with accents or background noise
- **medium**: Best quality without requiring a GPU
- **large**: Professional quality (slow without GPU)

For your Spanish learning use case, I'd recommend starting with **base** or **small**.

## Output

The script creates:
- `.srt` subtitle file (standard format, works with most video players)
- Files are saved in the `downloads/` folder (or custom directory)

## Using the Subtitles

### With VLC:
1. Open the video
2. Subtitle → Add Subtitle File
3. Select the .srt file

### With YouTube (if you have upload access):
1. Upload the .srt through YouTube Studio

### For sentence mining:
You can open .srt files in any text editor, or use tools like:
- Anki with subtitle2anki
- subs2srs
- Language Learning with Netflix (import custom subs)

## Troubleshooting

**"FFmpeg not found"**: Install FFmpeg and add it to your PATH

**Out of memory**: Use a smaller model (tiny or base)

**Slow processing**:
- Use smaller model
- GPU acceleration helps (requires CUDA for NVIDIA GPUs)
- A 20-minute video takes ~5-10 minutes on base model with CPU

## Tips for Better Results

- Whisper works best with clear audio
- Spanish (Spain vs Latin American) variants are handled automatically
- If subtitles have errors, try a larger model
- You can manually edit the .srt file to fix any mistakes
