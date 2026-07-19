from pathlib import Path

import auto_miner
from immersion_app.core.auto_mining import MiningCandidate


def _candidate(text="Hola mundo."):
    return MiningCandidate("hola", "Hola", text, "show.srt", "00:00:01,000")


def test_parse_args_uses_default_input_file_for_one_path():
    args = auto_miner.parse_args(["source.pdf"])

    assert args.input_file == Path("automine_inputs.txt")
    assert args.source_document == Path("source.pdf")
    assert args.source_lang == "es"
    assert args.target_lang == "en"


def test_review_approves_current_candidate_and_uses_source_text():
    added = []
    output = []

    approved = auto_miner.review_candidates(
        [_candidate()],
        lambda text: f"translated {text}",
        lambda *payload: added.append(payload),
        read_key=lambda: "enter",
        print_fn=lambda *values: output.append(" ".join(map(str, values))),
        clear_screen=lambda: None,
    )

    assert approved is True
    assert added == [("Hola mundo.", "Hola", "translated Hola")]
    assert any("Source: show.srt 00:00:01,000" in line for line in output)


def test_review_displays_queue_progress():
    output = []

    auto_miner.review_candidates(
        [_candidate()],
        lambda text: text,
        lambda *_: None,
        read_key=lambda: "escape",
        print_fn=lambda *values: output.append(" ".join(map(str, values))),
        clear_screen=lambda: None,
        queue_position=8,
        queue_total=13,
    )

    assert "Queue: word 8 of 13" in output


def test_review_cycles_right_before_approval():
    added = []
    keys = iter(["right", "enter"])
    candidates = [_candidate("Hola uno."), _candidate("Hola dos.")]

    auto_miner.review_candidates(
        candidates,
        lambda text: text,
        lambda *payload: added.append(payload),
        read_key=lambda: next(keys),
        print_fn=lambda *_: None,
        clear_screen=lambda: None,
    )

    assert added == [("Hola dos.", "Hola", "Hola")]


def test_review_uses_the_edited_translation_on_the_card_back():
    added = []
    keys = iter(["e", "enter"])

    auto_miner.review_candidates(
        [_candidate()],
        lambda text: f"machine {text}",
        lambda *payload: added.append(payload),
        read_key=lambda: next(keys),
        edit_translation=lambda initial: f"edited {initial}",
        print_fn=lambda *_: None,
        clear_screen=lambda: None,
    )

    assert added == [("Hola mundo.", "Hola", "edited machine Hola")]


def test_find_all_candidates_searches_every_query_before_review():
    queries = ["uno", "dos"]
    calls = []

    def find(query, contexts):
        calls.append((query, list(contexts)))
        return [_candidate(query)]

    original = auto_miner.find_candidates
    auto_miner.find_candidates = find
    try:
        matches = auto_miner.find_all_candidates(queries, ["context"])
    finally:
        auto_miner.find_candidates = original

    assert [match[0].sentence for match in matches] == queries
    assert calls == [("uno", ["context"]), ("dos", ["context"])]


def test_remove_query_from_queue_removes_only_one_matching_line(tmp_path):
    queue = tmp_path / "automine_inputs.txt"
    queue.write_text("uno\ndos\nuno\n", encoding="utf-8")

    auto_miner.remove_query_from_queue(queue, "uno")

    assert queue.read_text(encoding="utf-8") == "dos\nuno\n"


def test_main_removes_approved_query_only_after_card_creation(tmp_path, monkeypatch):
    queue = tmp_path / "automine_inputs.txt"
    queue.write_text("uno\ndos\n", encoding="utf-8")
    candidate_groups = [[_candidate("Uno.")], [_candidate("Dos.")]]
    reviewed = []

    class InteractiveInput:
        @staticmethod
        def isatty():
            return True

    def review(candidates, *args, **kwargs):
        reviewed.append((candidates, kwargs))
        return candidates[0].sentence == "Uno."

    monkeypatch.setattr(auto_miner, "load_source_contexts", lambda _: ["context"])
    monkeypatch.setattr(auto_miner, "find_all_candidates", lambda *_: candidate_groups)
    monkeypatch.setattr(auto_miner, "test_anki_connection", lambda: True)
    monkeypatch.setattr(auto_miner, "review_candidates", review)
    monkeypatch.setattr(auto_miner.sys, "stdin", InteractiveInput())

    assert auto_miner.main([str(queue), "source.srt"]) == 0
    assert queue.read_text(encoding="utf-8") == "dos\n"
    assert [call[1]["queue_position"] for call in reviewed] == [1, 2]
    assert all(call[1]["queue_total"] == 2 for call in reviewed)
