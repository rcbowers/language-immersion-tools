#!/usr/bin/env python3
"""
YouTube Spanish Subtitle Generator (GPU-Accelerated)
Downloads YouTube videos and generates Spanish subtitles using Whisper AI with GPU support
"""

import argparse
import os
import re
import sys
from pathlib import Path

import torch
import whisper
from yt_dlp import YoutubeDL


def get_device():
    """Detect and return the best available device (CUDA GPU or CPU)"""
    if torch.cuda.is_available():
        device = "cuda"
        gpu_name = torch.cuda.get_device_name(0)
        print(f"🚀 GPU detected: {gpu_name}")
        print(f"   CUDA version: {torch.version.cuda}")
        print(f"   GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
    else:
        device = "cpu"
        print("💻 No GPU detected, using CPU")
    return device


def sanitize_filename(filename):
    """Remove or replace invalid characters from filename"""
    # Replace invalid Windows filename characters
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)
    # Remove any leading/trailing spaces or dots
    sanitized = sanitized.strip('. ')
    return sanitized


def download_video(url, output_dir="downloads"):
    """Download YouTube video using yt-dlp"""
    print(f"\n📥 Downloading video from: {url}")

    Path(output_dir).mkdir(exist_ok=True)

    # First, download the full video file
    print("📹 Downloading full video file...")
    video_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'{output_dir}/%(title)s.%(ext)s',
        'merge_output_format': 'mp4',
        'quiet': False,
    }

    with YoutubeDL(video_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_title = info['title']
        video_id = info['id']
        sanitized_title = sanitize_filename(video_title)
        video_file = f"{output_dir}/{sanitized_title}.mp4"

    print(f"✅ Video downloaded: {video_title}")

    # Now download audio for transcription (existing pipeline)
    print("🎵 Extracting audio for transcription...")
    audio_opts = {
        'format': 'bestaudio/best',  # Audio only for faster download
        'outtmpl': f'{output_dir}/%(id)s_audio.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
    }

    with YoutubeDL(audio_opts) as ydl:
        ydl.extract_info(url, download=True)
        audio_file = f"{output_dir}/{video_id}_audio.mp3"

    print(f"✅ Audio extracted for transcription")
    return audio_file, video_file, video_title


def generate_subtitles(audio_file, model_size="base", language="es", device="cuda"):
    """Generate subtitles using Whisper with GPU acceleration"""
    print(f"\n🤖 Loading Whisper model: {model_size} on {device.upper()}")
    model = whisper.load_model(model_size, device=device)

    print(f"🎯 Transcribing audio (language: {language})...")

    # Use fp16 for GPU acceleration (faster inference)
    use_fp16 = device == "cuda"
    if use_fp16:
        print("⚡ Using FP16 (half precision) for faster GPU inference")

    result = model.transcribe(
        audio_file,
        language=language,
        task="transcribe",
        verbose=True,
        fp16=use_fp16
    )

    return result


def save_subtitles(result, output_file):
    """Save subtitles in SRT format"""
    print(f"\n💾 Saving subtitles to: {output_file}")

    with open(output_file, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(result['segments'], start=1):
            # SRT format: index, timestamp, text
            start = format_timestamp(segment['start'])
            end = format_timestamp(segment['end'])
            text = segment['text'].strip()

            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")

    print(f"✅ Subtitles saved successfully!")


def format_timestamp(seconds):
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def main():
    parser = argparse.ArgumentParser(
        description="Generate Spanish subtitles for YouTube videos using Whisper AI (GPU-accelerated)"
    )
    # parser.add_argument(
    #     "url",
    #     help="YouTube video URL"
    # )
    parser.add_argument(
        "-m", "--model",
        choices=["tiny", "base", "small", "medium", "large"],
        default="large",
        help="Whisper model size (default: base). Larger = more accurate but slower."
    )
    parser.add_argument(
        "-l", "--language",
        default="es",
        help="Language code (default: es for Spanish)"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="downloads",
        help="Output directory (default: downloads)"
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="Keep the downloaded audio file"
    )
    parser.add_argument(
        "--keep-video",
        action="store_true",
        default=True,
        help="Keep the downloaded video file (default: True)"
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU usage even if GPU is available"
    )

    args = parser.parse_args()

    # Detect device
    if args.cpu:
        device = "cpu"
        print("💻 CPU mode forced by user")
    else:
        device = get_device()

    for url in [
        'https://youtu.be/ZZiY6Q4Lgus?si=XMuxMACwNW-Sy2_z',
        'https://youtu.be/AQF519M7xB0?si=KgCSAxXAMi_it6No',
        'https://youtu.be/AQF519M7xB0?si=98rgj8lKVgHQTUiX',
        'https://youtu.be/gZWpD0VsRMg?si=WRY8nO-GMTEkIHGp',
        'https://youtu.be/AEtZekVZJvs?si=Cjn2600rVG3v3CAF',
        'https://youtu.be/Lq0MsaJdB08?si=Tov2_TF40frIuX3i',
        'https://youtu.be/sw_Xh7DFQTs?si=JdHlrHAiCDF7g1FS',
        'https://youtu.be/lwYBVbFVqxg?si=CBCOKjDJ79p68082',
        'https://youtu.be/7ZyAxYCbHWQ?si=l9M7gsU24LJdooUO',
        'https://youtu.be/Gm-BOd0Khmk?si=iaJvCEYutfE67jSQ',
        'https://youtu.be/vjK2cuHWXVs?si=1z8eh-kof8fY4yFo', # s2e10

#        'https://youtu.be/sM-RwR_cZOc?si=XwCPQkvk7G6RHaF2',
  #      'https://youtu.be/q3rGg_S5oLs?si=B8YTWTLfG7YUtfCB',
 #       'https://youtu.be/4DfM5vK1FN0?si=g_3n9ktWTo-r-Sxf',
        #'https://youtu.be/7L8yRoiOljk?si=hE8N6NmB854uUw_L',
        #'https://youtu.be/GxTIupAEe1Q?si=ZdFjbtvPEnuZIuj-',
       # 'https://youtu.be/KYZrPGlFyAg?si=wy3sNy5C3ZR-Sw5K',
       # 'https://youtu.be/gWxdJtMYgao?si=vux6uedAJ-_7JaT9',
       # 'https://youtu.be/3SJ-pzhpMso?si=a5rZd_KobpNGfy0I',
       # 'https://youtu.be/O4jA2YIjJ7I?si=mIJ3F_n2U60OGvn3',
       # 'https://youtu.be/0utr0LrT_Ns?si=Ruzfy8gd8mh9eoCB',
       # 'https://youtu.be/GS7dBJYRvd0?si=OQlyV7XTWJs8_C9H',
       # 'https://youtu.be/jxKoIWmtuM8?si=7jo7CbUi-g7i6ddT',
       # 'https://youtu.be/p-rjN7NfKw4?si=LJCn08LWQrnYWjcF',
        #'https://youtu.be/U-yzUxXJQq8?si=obIhVikfIEEwF9b2',

    ]:

        try:
            # Step 1: Download video
            audio_file, video_file, video_title = download_video(url, args.output_dir)

            # Step 2: Generate subtitles with GPU
            result = generate_subtitles(audio_file, args.model, args.language, device)

            # Step 3: Save subtitles with sanitized title
            sanitized_title = sanitize_filename(video_title)
            subtitle_file = f"{args.output_dir}/{sanitized_title}.srt"
            save_subtitles(result, subtitle_file)

            # Step 4: Cleanup
            if not args.keep_audio:
                print(f"\n🧹 Removing audio file: {audio_file}")
                os.remove(audio_file)

            if not args.keep_video:
                print(f"\n🧹 Removing video file: {video_file}")
                os.remove(video_file)

            print(f"\n🎉 Done! Your files are ready:")
            print(f"   Video: {video_file}")
            print(f"   Subtitles: {subtitle_file}")

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
