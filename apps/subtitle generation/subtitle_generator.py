#!/usr/bin/env python3
"""
Subtitle generator for YouTube and local video files using Whisper.
"""

import argparse
import re
import sys
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}


def sanitize_filename(filename):
    """Remove or replace invalid characters from filename."""
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, "_", filename)
    return sanitized.strip(". ")


def choose_device(use_gpu):
    """Choose inference device from CLI flags and local hardware."""
    if use_gpu:
        try:
            import torch
        except ImportError:
            print("Warning: --gpu requested but torch is not installed. Falling back to CPU.")
            return "cpu"

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print(f"GPU enabled: {gpu_name}")
            return "cuda"
        print("Warning: --gpu requested but CUDA is unavailable. Falling back to CPU.")
    return "cpu"


def read_urls(url_file):
    """Read URLs from a text file (one URL per line)."""
    url_path = Path(url_file)
    if not url_path.exists():
        raise FileNotFoundError(f"URL file not found: {url_file}")

    urls = []
    for line in url_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        urls.append(stripped)
    return urls


def find_video_files(folder_path):
    """Recursively find supported video files in a folder."""
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise NotADirectoryError(f"Invalid video folder: {folder_path}")

    return [
        file
        for file in folder.rglob("*")
        if file.is_file() and file.suffix.lower() in VIDEO_EXTENSIONS
    ]


def download_video(url, output_dir):
    """Download YouTube video + audio using yt-dlp."""
    from yt_dlp import YoutubeDL

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    print(f"Downloading video from: {url}")

    video_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
        "merge_output_format": "mp4",
        "quiet": False,
    }
    with YoutubeDL(video_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_title = info["title"]
        video_id = info["id"]

    sanitized_title = sanitize_filename(video_title)
    video_file = Path(output_dir) / f"{sanitized_title}.mp4"

    audio_opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{output_dir}/%(id)s_audio.%(ext)s",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": False,
    }
    with YoutubeDL(audio_opts) as ydl:
        ydl.extract_info(url, download=True)

    audio_file = Path(output_dir) / f"{video_id}_audio.mp3"
    return audio_file, video_file, video_title


def load_model(model_size, device):
    """Load Whisper model once per run."""
    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError(
            "openai-whisper and its dependencies are required. "
            "Install with: pip install openai-whisper"
        ) from exc

    print(f"Loading Whisper model '{model_size}' on {device}...")
    return whisper.load_model(model_size, device=device)


def generate_subtitles(model, media_file, language, device):
    """Generate subtitles using Whisper model."""
    use_fp16 = device == "cuda"
    print(f"Transcribing: {media_file}")
    return model.transcribe(
        str(media_file),
        language=language,
        task="transcribe",
        verbose=True,
        fp16=use_fp16,
    )


def save_subtitles(result, output_file):
    """Save subtitles in SRT format."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for i, segment in enumerate(result["segments"], start=1):
            start = format_timestamp(segment["start"])
            end = format_timestamp(segment["end"])
            text = segment["text"].strip()
            handle.write(f"{i}\n")
            handle.write(f"{start} --> {end}\n")
            handle.write(f"{text}\n\n")
    print(f"Wrote subtitles: {output_path}")


def format_timestamp(seconds):
    """Convert seconds to SRT timestamp format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def youtube_mode(args, model, device):
    urls = read_urls(args.url_file)
    if not urls:
        raise ValueError(f"No URLs found in: {args.url_file}")

    output_dir = args.output_dir or "downloads"
    failures = 0
    for url in urls:
        try:
            audio_file, video_file, video_title = download_video(url, output_dir)
            result = generate_subtitles(model, audio_file, args.language, device)
            subtitle_file = Path(output_dir) / f"{sanitize_filename(video_title)}.srt"
            save_subtitles(result, subtitle_file)

            if not args.keep_audio and audio_file.exists():
                audio_file.unlink()
            if not args.keep_video and video_file.exists():
                video_file.unlink()
        except Exception as exc:
            failures += 1
            print(f"Error processing URL '{url}': {exc}")

    return failures, len(urls)


def folder_mode(args, model, device):
    video_files = find_video_files(args.video_folder)
    if not video_files:
        raise ValueError(f"No supported video files found in: {args.video_folder}")

    failures = 0
    for video_file in video_files:
        try:
            result = generate_subtitles(model, video_file, args.language, device)
            if args.output_dir:
                subtitle_file = Path(args.output_dir) / f"{video_file.stem}.srt"
            else:
                subtitle_file = video_file.with_suffix(".srt")
            save_subtitles(result, subtitle_file)
        except Exception as exc:
            failures += 1
            print(f"Error processing video '{video_file}': {exc}")

    return failures, len(video_files)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate subtitles with Whisper from YouTube URLs or local videos."
    )
    parser.add_argument(
        "--mode",
        choices=["youtube", "folder"],
        required=True,
        help="Input mode: youtube downloads from URL list, folder scans local videos.",
    )
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Use CUDA GPU if available; otherwise falls back to CPU.",
    )
    parser.add_argument(
        "--url-file",
        help="Path to text file containing one YouTube URL per line (youtube mode).",
    )
    parser.add_argument(
        "--video-folder",
        help="Path to folder containing local videos to transcribe (folder mode).",
    )
    parser.add_argument(
        "-m",
        "--model",
        choices=["tiny", "base", "small", "medium", "large"],
        default="medium",
        help="Whisper model size.",
    )
    parser.add_argument(
        "-l",
        "--language",
        default="es",
        help="Language code for transcription (default: es).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help="Output directory. Default: youtube mode uses downloads, folder mode writes next to video.",
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="Keep downloaded audio file in youtube mode.",
    )
    parser.add_argument(
        "--keep-video",
        action="store_true",
        default=True,
        help="Keep downloaded video file in youtube mode.",
    )
    args = parser.parse_args()

    if args.mode == "youtube" and not args.url_file:
        parser.error("--url-file is required when --mode youtube")
    if args.mode == "folder" and not args.video_folder:
        parser.error("--video-folder is required when --mode folder")
    return args


def main():
    args = parse_args()
    device = choose_device(args.gpu)
    model = load_model(args.model, device)

    try:
        if args.mode == "youtube":
            failures, total = youtube_mode(args, model, device)
        else:
            failures, total = folder_mode(args, model, device)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"Fatal error: {exc}")
        sys.exit(1)

    print(f"Completed {total - failures}/{total} items.")
    if failures == total:
        sys.exit(1)


if __name__ == "__main__":
    main()
