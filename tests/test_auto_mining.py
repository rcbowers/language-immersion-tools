from immersion_app.core.auto_mining import find_candidates, normalize_for_match
from immersion_app.media.source_context import SourceContext


def test_normalize_folds_accents_and_apostrophes():
    assert normalize_for_match("Él dijo: don’t.") == "el dijo: don't."


def test_find_candidates_uses_source_wording_for_accent_flexible_phrase():
    contexts = [SourceContext("Porque eres un brujo, Harry.", "book.pdf", "Page 5")]

    candidates = find_candidates("eres un brujo, harry", contexts)

    assert len(candidates) == 1
    assert candidates[0].matched_text == "eres un brujo, Harry"
    assert candidates[0].sentence == "Porque eres un brujo, Harry."
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
