from immersion_app.core.auto_mining import (
    adjust_context_window,
    context_window_bounds,
    find_candidates,
    normalize_for_match,
    render_context_neighbor_words,
    render_context_window,
)
from immersion_app.media.source_context import SourceContext


def test_normalize_folds_accents_and_apostrophes():
    assert normalize_for_match("Él dijo: don’t.") == "el dijo: don't."


def test_find_candidates_uses_source_wording_for_accent_flexible_phrase():
    contexts = [SourceContext("Porque eres un buen amigo, Pablo.", "book.pdf", "Page 5")]

    candidates = find_candidates("eres un buen amigo, pablo", contexts)

    assert len(candidates) == 1
    assert candidates[0].matched_text == "eres un buen amigo, Pablo"
    assert candidates[0].sentence == "Porque eres un buen amigo, Pablo."
    assert candidates[0].location == "Page 5"


def test_find_candidates_does_not_match_inside_a_larger_word():
    contexts = [SourceContext("Holanda no es hola.", "book.pdf", "Page 1")]

    candidates = find_candidates("hola", contexts)

    assert [candidate.matched_text for candidate in candidates] == ["hola"]


def test_find_candidates_matches_all_occurrences():
    contexts = [
        SourceContext("Hola mundo.", "book.pdf", "Page 1"),
        SourceContext("Otra hola.", "book.pdf", "Page 2"),
    ]

    assert len(find_candidates("hola", contexts)) == 2


def test_context_window_preserves_the_selected_occurrence_and_word_punctuation():
    candidate = find_candidates(
        "tres", [SourceContext("Uno dos tres, cuatro.", "book.pdf", "Page 1")]
    )[0]
    bounds = context_window_bounds(candidate)

    bounds = adjust_context_window(candidate, bounds, "start_forward")
    bounds = adjust_context_window(candidate, bounds, "start_forward")
    bounds = adjust_context_window(candidate, bounds, "start_forward")
    bounds = adjust_context_window(candidate, bounds, "end_backward")
    bounds = adjust_context_window(candidate, bounds, "end_backward")

    assert render_context_window(candidate, bounds) == "tres,"


def test_context_preview_shows_at_most_five_neighboring_words_per_side():
    candidate = find_candidates(
        "seis", [SourceContext("Uno dos tres cuatro cinco seis siete ocho nueve diez once doce.", "book.pdf", "Page 1")]
    )[0]
    bounds = (5, 6)

    assert render_context_neighbor_words(candidate, bounds) == (
        "Uno dos tres cuatro cinco",
        "siete ocho nueve diez once",
    )


def test_context_window_expands_into_the_neighboring_words():
    candidate = find_candidates(
        "centro",
        [
            SourceContext("Uno dos tres cuatro cinco seis.", "book.pdf", "Page 1"),
            SourceContext("Centro aqui.", "book.pdf", "Page 1"),
            SourceContext("Siete ocho nueve diez once doce.", "book.pdf", "Page 1"),
        ],
    )[0]
    bounds = context_window_bounds(candidate)

    expanded_start = adjust_context_window(candidate, bounds, "start_backward")
    expanded_end = adjust_context_window(candidate, bounds, "end_forward")

    assert render_context_window(candidate, expanded_start) == "seis. Centro aqui."
    assert render_context_window(candidate, expanded_end) == "Centro aqui. Siete"
