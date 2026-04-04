#!/usr/bin/env python3
"""Tests for subtitle matching helpers."""

import tempfile
import unittest
from pathlib import Path

from immersion_app.media.subtitle_matching import find_best_srt_for_video, normalize_media_stem


class SubtitleMatchingTests(unittest.TestCase):
    def test_normalize_media_stem_handles_qt_suffix(self):
        self.assertEqual(
            normalize_media_stem("31 minutos - Episodio 2＊06 - Lulo Serrucho.qt_compatible.mp4"),
            "31 minutos episodio 2 06 lulo serrucho",
        )

    def test_exact_match_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "clip.mp4"
            srt = root / "clip.srt"
            video.write_text("", encoding="utf-8")
            srt.write_text("", encoding="utf-8")
            self.assertEqual(find_best_srt_for_video(str(video)), str(srt))

    def test_qt_compatible_matches_original_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "show.qt_compatible.mp4"
            srt = root / "show.srt"
            video.write_text("", encoding="utf-8")
            srt.write_text("", encoding="utf-8")
            self.assertEqual(find_best_srt_for_video(str(video)), str(srt))

    def test_unicode_variant_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "31 minutos - Episodio 2＊06 - Lulo Serrucho.mp4"
            srt = root / "31 minutos - Episodio 2_06 - Lulo Serrucho.srt"
            video.write_text("", encoding="utf-8")
            srt.write_text("", encoding="utf-8")
            self.assertEqual(find_best_srt_for_video(str(video)), str(srt))

    def test_no_match_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "abc.mp4"
            other = root / "xyz.srt"
            video.write_text("", encoding="utf-8")
            other.write_text("", encoding="utf-8")
            self.assertIsNone(find_best_srt_for_video(str(video)))


if __name__ == "__main__":
    unittest.main()
