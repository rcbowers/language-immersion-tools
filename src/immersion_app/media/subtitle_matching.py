#!/usr/bin/env python3
"""Helpers for matching video files to subtitle files."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower()
    text = re.sub(r"\bqt[\s_\-]*compatible\b", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_media_stem(name: str) -> str:
    return _normalize_text(Path(name).stem)


def _tokenize(name: str) -> set[str]:
    norm = _normalize_text(name)
    if not norm:
        return set()
    return set(norm.split())


def _overlap_score(video_tokens: set[str], srt_tokens: set[str]) -> tuple[int, int]:
    if not video_tokens or not srt_tokens:
        return (0, 0)
    overlap = len(video_tokens & srt_tokens)
    union = len(video_tokens | srt_tokens)
    return (overlap, union)


def find_best_srt_for_video(video_path: str) -> str | None:
    video = Path(video_path)
    if not video.exists():
        return None

    exact = video.with_suffix(".srt")
    if exact.exists():
        return str(exact)

    parent = video.parent
    candidates = sorted(parent.glob("*.srt"))
    if not candidates:
        return None

    video_norm = normalize_media_stem(video.name)
    video_tokens = _tokenize(video.stem)

    exact_norm = [c for c in candidates if normalize_media_stem(c.name) == video_norm]
    if exact_norm:
        return str(exact_norm[0])

    ranked = []
    for candidate in candidates:
        overlap, union = _overlap_score(video_tokens, _tokenize(candidate.stem))
        if overlap == 0:
            continue
        ranked.append((overlap, union, len(candidate.stem), candidate.name, candidate))

    if not ranked:
        return None

    ranked.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))
    return str(ranked[0][4])
