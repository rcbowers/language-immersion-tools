"""Tests for the standalone Anki vocabulary counter CLI helpers."""

from pathlib import Path

import matplotlib.pyplot as plt

import vocab_counter


def test_plot_filename_sanitizes_deck_name():
    assert vocab_counter.plot_filename('Spanish: Mining/Deck') == Path(
        "Spanish__Mining_Deck_word_distribution.png"
    )


def test_create_word_distribution_plot_sorts_by_count_then_word(
    tmp_path,
    monkeypatch,
):
    recorded = {}
    original_subplots = plt.subplots

    def capture_subplots(*args, **kwargs):
        figure, axis = original_subplots(*args, **kwargs)
        recorded["axis"] = axis
        return figure, axis

    monkeypatch.setattr(vocab_counter.plt, "subplots", capture_subplots)
    output_path = tmp_path / "distribution.png"

    created = vocab_counter.create_word_distribution_plot(
        {"zorro": 2, "abeja": 4, "barco": 2},
        output_path,
    )

    assert created is True
    assert output_path.is_file()
    assert output_path.stat().st_size > 0
    assert [label.get_text() for label in recorded["axis"].get_xticklabels()] == [
        "abeja",
        "barco",
        "zorro",
    ]
    assert [patch.get_height() for patch in recorded["axis"].patches] == [4, 2, 2]


def test_create_word_distribution_plot_skips_empty_frequencies(
    tmp_path,
    capsys,
):
    output_path = tmp_path / "distribution.png"

    created = vocab_counter.create_word_distribution_plot({}, output_path)

    assert created is False
    assert not output_path.exists()
    assert "No words to plot." in capsys.readouterr().out
