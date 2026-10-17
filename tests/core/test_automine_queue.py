import pytest

from immersion_app.core.automine_queue import (
    is_url,
    parse_queue_sections,
    remove_query_from_section,
)

QUEUE = """\
orphan
# https://example.com/a
uno

dos
# "C:/books/libro.pdf"
uno
# 'empty.srt'
"""


def test_parse_queue_sections_groups_words_and_strips_quotes():
    sections = parse_queue_sections(QUEUE)

    assert [(s.source, s.queries) for s in sections] == [
        ("https://example.com/a", ["uno", "dos"]),
        ("C:/books/libro.pdf", ["uno"]),
    ]


def test_parse_queue_sections_empty_text():
    assert parse_queue_sections("") == []


def test_is_url():
    assert is_url("https://example.com") and is_url("HTTP://example.com")
    assert not is_url("C:/books/libro.pdf")


def test_remove_query_from_section_only_touches_named_section():
    result = remove_query_from_section(QUEUE, "C:/books/libro.pdf", "uno")

    assert "# https://example.com/a\nuno\n" in result
    assert '# "C:/books/libro.pdf"\n# \'empty.srt\'' in result


def test_remove_query_from_section_removes_first_match_only():
    text = "# a\nuno\nuno\n"

    assert remove_query_from_section(text, "a", "uno") == "# a\nuno\n"


def test_remove_query_from_section_raises_when_missing():
    with pytest.raises(ValueError):
        remove_query_from_section("# a\nuno\n", "b", "uno")
