"""Extract audio from YouTube or local video files."""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

import ffmpeg
from yt_dlp import YoutubeDL

from immersion_app.core.logging_config import setup_cli_logging

logger = logging.getLogger(__name__)


def is_youtube_url(input_string):
    return bool(re.match(r"(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/", input_string))


def sanitize_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', "_", filename).strip(". ")


def extract_audio_from_youtube(url, output_dir):
    print(f"Downloading audio from YouTube: {url}")
    audio_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "quiet": False,
        "no_warnings": False,
    }
    with YoutubeDL(audio_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_title = info.get("title", "audio")
        output_file = output_dir / f"{sanitize_filename(video_title)}.mp3"
        print(f"Saved to: {output_file}")
        return output_file


def extract_audio_from_local_file(video_path, output_dir):
    video_file = Path(video_path)
    if not video_file.exists():
        raise FileNotFoundError(f"File not found: {video_path}")
    output_file = output_dir / f"{sanitize_filename(video_file.stem)}.mp3"
    stream = ffmpeg.input(str(video_file))
    stream = ffmpeg.output(stream, str(output_file), acodec="libmp3lame", audio_bitrate="192k")
    ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
    print(f"Saved to: {output_file}")
    return output_file


def main():
    setup_cli_logging()
    logger.info("Audio extraction tool starting")
    parser = argparse.ArgumentParser(description="Extract audio from YouTube videos or local video files as MP3")
    parser.add_argument("input", help="YouTube URL or path to local video file")
    parser.add_argument("-o", "--output-dir", default="audio_files")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir.resolve()}")
    try:
        if is_youtube_url(args.input):
            logger.info(f"Extracting audio from YouTube: {args.input}")
            extract_audio_from_youtube(args.input, output_dir)
        else:
            logger.info(f"Extracting audio from local file: {args.input}")
            extract_audio_from_local_file(args.input, output_dir)
    except Exception as exc:
        logger.error(f"Audio extraction failed: {exc}", exc_info=True)
        return 1
    logger.info("Audio extraction completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

