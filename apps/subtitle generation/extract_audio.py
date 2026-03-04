#!/usr/bin/env python3
"""
Extract audio from YouTube videos or local video files and save as MP3.

This script accepts either a YouTube URL or a path to a local video file,
extracts the audio, and saves it as an MP3 file in the audio_files/ directory.
"""

import argparse
import sys
import re
from pathlib import Path
from urllib.parse import urlparse
import ffmpeg
from yt_dlp import YoutubeDL


def is_youtube_url(input_string):
    """Check if the input string is a YouTube URL."""
    youtube_patterns = [
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/',
    ]
    return any(re.match(pattern, input_string) for pattern in youtube_patterns)


def sanitize_filename(filename):
    """Sanitize filename for Windows compatibility."""
    # Remove invalid characters for Windows filenames
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip('. ')
    return sanitized


def extract_audio_from_youtube(url, output_dir):
    """Extract audio from a YouTube video URL."""
    print(f"📥 Downloading audio from YouTube: {url}")

    # Configure yt-dlp options
    audio_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_dir / '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
        'no_warnings': False,
    }

    try:
        with YoutubeDL(audio_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'audio')
            sanitized_title = sanitize_filename(video_title)
            output_file = output_dir / f"{sanitized_title}.mp3"
            print(f"✅ Audio extracted successfully!")
            print(f"📁 Saved to: {output_file}")
            return output_file
    except Exception as e:
        print(f"❌ Error downloading from YouTube: {e}")
        sys.exit(1)


def extract_audio_from_local_file(video_path, output_dir):
    """Extract audio from a local video file."""
    video_file = Path(video_path)

    # Check if file exists
    if not video_file.exists():
        print(f"❌ Error: File not found: {video_path}")
        sys.exit(1)

    # Check if file is a video (basic extension check)
    video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm', '.m4v']
    if video_file.suffix.lower() not in video_extensions:
        print(f"⚠️  Warning: '{video_file.suffix}' may not be a video file")

    print(f"🎵 Extracting audio from: {video_file.name}")

    # Create output filename
    output_filename = sanitize_filename(video_file.stem) + '.mp3'
    output_file = output_dir / output_filename

    try:
        # Use ffmpeg to extract audio
        stream = ffmpeg.input(str(video_file))
        stream = ffmpeg.output(stream, str(output_file), acodec='libmp3lame', audio_bitrate='192k')
        ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)

        print(f"✅ Audio extracted successfully!")
        print(f"📁 Saved to: {output_file}")
        return output_file
    except ffmpeg.Error as e:
        print(f"❌ Error extracting audio: {e.stderr.decode() if e.stderr else str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


def main():
    """Main function to parse arguments and extract audio."""
    parser = argparse.ArgumentParser(
        description='Extract audio from YouTube videos or local video files as MP3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract from YouTube URL
  python extract_audio.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

  # Extract from local video file
  python extract_audio.py "C:/Videos/my_video.mp4"
  python extract_audio.py "/path/to/video.mkv"

  # Specify custom output directory
  python extract_audio.py "video.mp4" --output-dir "my_audio"
        """
    )

    parser.add_argument(
        'input',
        help='YouTube URL or path to local video file'
    )

    parser.add_argument(
        '-o', '--output-dir',
        default='audio_files',
        help='Output directory for extracted audio files (default: audio_files)'
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    print(f"📂 Output directory: {output_dir.absolute()}\n")

    # Determine input type and extract audio
    if is_youtube_url(args.input):
        extract_audio_from_youtube(args.input, output_dir)
    else:
        extract_audio_from_local_file(args.input, output_dir)

    print("\n🎉 Done!")


if __name__ == "__main__":
    main()
