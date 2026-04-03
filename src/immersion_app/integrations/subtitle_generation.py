#!/usr/bin/env python3
"""Whisper subtitle generation wrapper for local video files."""

import os
from pathlib import Path


def _format_srt_timestamp(seconds):
    total_ms = int(max(0, seconds) * 1000)
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    s = total_seconds % 60
    total_minutes = total_seconds // 60
    m = total_minutes % 60
    h = total_minutes // 60
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def generate_srt_from_video(video_path, output_path=None, model_size="base", language="es", progress_callback=None):
    video_path = str(video_path)
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if output_path is None:
        output_path = str(Path(video_path).with_suffix(".srt"))

    if progress_callback:
        progress_callback("Loading Whisper model...")

    import torch
    import whisper

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = whisper.load_model(model_size, device=device)

    if progress_callback:
        progress_callback("Transcribing audio...")

    result = model.transcribe(video_path, language=language)
    segments = result.get("segments", [])

    if progress_callback:
        progress_callback("Saving subtitles...")

    with open(output_path, "w", encoding="utf-8") as handle:
        for idx, seg in enumerate(segments, start=1):
            start = _format_srt_timestamp(seg.get("start", 0.0))
            end = _format_srt_timestamp(seg.get("end", 0.0))
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            handle.write(f"{idx}\n")
            handle.write(f"{start} --> {end}\n")
            handle.write(f"{text}\n\n")

    return output_path
