"""Edge cases for the SRT parser: real-world files are messy."""

from __future__ import annotations

import pytest

from immersion_app.media.subtitle_parser import SRTParser


def test_multiline_cue_is_joined_with_spaces():
    parser = SRTParser.from_text("1\n00:00:01,000 --> 00:00:02,000\nPrimera linea\nsegunda linea\n")
    assert parser.subtitles[0].text == "Primera linea segunda linea"


def test_crlf_line_endings():
    parser = SRTParser.from_text("1\r\n00:00:01,000 --> 00:00:02,000\r\nHola\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nAdios\r\n")
    assert [s.text for s in parser.subtitles] == ["Hola", "Adios"]


def test_utf8_bom_file(tmp_path):
    path = tmp_path / "bom.srt"
    path.write_bytes("﻿1\n00:00:01,000 --> 00:00:02,000\nHola\n".encode("utf-8"))
    parser = SRTParser.from_file(str(path))
    assert [s.index for s in parser.subtitles] == [1] and parser.subtitles[0].text == "Hola"


def test_non_ascii_text_and_words(tmp_path):
    path = tmp_path / "ja.srt"
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\n¿Qué pasó, niño?\n", encoding="utf-8")
    parser = SRTParser.from_file(str(path))
    assert [w.word for w in parser.subtitles[0].words] == ["Qué", "pasó", "niño"]


def test_non_utf8_file_raises_rather_than_returning_garbage(tmp_path):
    path = tmp_path / "latin1.srt"
    path.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nQué pasó\n".encode("latin-1"))
    with pytest.raises(UnicodeDecodeError):
        SRTParser.from_file(str(path))


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        SRTParser.from_file("definitely/not/here.srt")


def test_malformed_timestamps_are_skipped_without_losing_good_cues():
    text = (
        "1\n00:00:01,000 --> 00:00:02,000\nBuena\n\n"
        "2\n00:00:0X,000 --> 00:00:04,000\nMala\n\n"
        "3\nno arrow here\nTexto\n\n"
        "4\n00:00:05,000 --> 00:00:06,000\nOtra buena\n"
    )
    assert [s.text for s in SRTParser.from_text(text).subtitles] == ["Buena", "Otra buena"]


def test_dot_milliseconds_are_not_accepted_and_cue_is_skipped():
    parser = SRTParser.from_text("1\n00:00:01.000 --> 00:00:02.000\nHola\n")
    assert parser.subtitles == []


@pytest.mark.parametrize("value, ms", [("00:00:00,000", 0), ("00:01:01,500", 61_500), ("01:00:00,001", 3_600_001)])
def test_parse_timestamp(value, ms):
    assert SRTParser.parse_timestamp(value) == ms


def test_parse_timestamp_invalid():
    with pytest.raises(ValueError):
        SRTParser.parse_timestamp("1:2:3")


def test_cue_without_index_line_is_inferred():
    parser = SRTParser.from_text("00:00:01,000 --> 00:00:02,000\nSin indice\n\n00:00:03,000 --> 00:00:04,000\nOtro\n")
    assert [(s.index, s.text) for s in parser.subtitles] == [(1, "Sin indice"), (2, "Otro")]


def test_position_settings_after_end_timestamp_are_ignored():
    parser = SRTParser.from_text("1\n00:00:01,000 --> 00:00:02,000 X1:10 X2:20\nHola\n")
    assert parser.subtitles[0].end_ms == 2000


def test_cues_are_sorted_by_start_time():
    parser = SRTParser.from_text("2\n00:00:05,000 --> 00:00:06,000\nSegunda\n\n1\n00:00:01,000 --> 00:00:02,000\nPrimera\n")
    assert [s.text for s in parser.subtitles] == ["Primera", "Segunda"]


def test_empty_text_cue_and_empty_input():
    assert SRTParser.from_text("1\n00:00:01,000 --> 00:00:02,000\n").subtitles == []
    assert SRTParser.from_text("").subtitles == []
    assert SRTParser.from_text("   \n\n  ").subtitles == []


def test_overlapping_cues_lookup_prefers_latest_started():
    parser = SRTParser.from_text(
        "1\n00:00:01,000 --> 00:00:05,000\nLarga\n\n2\n00:00:02,000 --> 00:00:03,000\nCorta\n"
    )
    assert parser.get_subtitle_at_time(2500).text == "Corta"
    assert parser.get_subtitle_at_time(1500).text == "Larga"
    # Known limitation: once a later cue has started and ended, the earlier long cue is no longer found.
    assert parser.get_subtitle_at_time(4000) is None


def test_lookup_boundaries_and_empty_parser():
    parser = SRTParser.from_text("1\n00:00:01,000 --> 00:00:02,000\nHola\n")
    assert parser.get_subtitle_at_time(999) is None
    assert parser.get_subtitle_at_time(1000).text == "Hola"
    assert parser.get_subtitle_at_time(2000).text == "Hola"  # end is inclusive
    assert parser.get_subtitle_at_time(2001) is None
    assert SRTParser().get_subtitle_at_time(0) is None
