import os
from pathlib import Path

import auto_miner
from immersion_app.core.auto_mining import MiningCandidate


def _candidate(text="Hola mundo."):
    return MiningCandidate("hola", "Hola", text, "show.srt", "00:00:01,000")


def test_parse_args_uses_default_input_file_for_one_path():
    args = auto_miner.parse_args(["source.pdf"])

    assert args.input_file == auto_miner.PROJECT_ROOT / "automine_inputs.txt"
    assert args.source_document == Path("source.pdf")
    assert args.source_lang == "es"
    assert args.target_lang == "en"


def test_parse_args_leaves_source_document_none_when_omitted():
    args = auto_miner.parse_args([])

    assert args.input_file == auto_miner.PROJECT_ROOT / "automine_inputs.txt"
    assert args.source_document is None


def test_remember_recent_source_adds_newest_first_and_dedupes(tmp_path, monkeypatch):
    recent_path = tmp_path / "automine_recent_sources.json"
    monkeypatch.setattr(auto_miner, "RECENT_SOURCES_PATH", recent_path)
    older = tmp_path / "older.pdf"
    newer = tmp_path / "newer.pdf"
    older.write_text("x")
    newer.write_text("x")

    auto_miner.remember_recent_source(older)
    auto_miner.remember_recent_source(newer)
    auto_miner.remember_recent_source(older)

    assert auto_miner.load_recent_sources() == [str(older.resolve()), str(newer.resolve())]


def test_remember_recent_source_caps_list_length(tmp_path, monkeypatch):
    recent_path = tmp_path / "automine_recent_sources.json"
    monkeypatch.setattr(auto_miner, "RECENT_SOURCES_PATH", recent_path)
    monkeypatch.setattr(auto_miner, "MAX_RECENT_SOURCES", 2)

    for name in ("a.pdf", "b.pdf", "c.pdf"):
        path = tmp_path / name
        path.write_text("x")
        auto_miner.remember_recent_source(path)

    recent = auto_miner.load_recent_sources()
    assert len(recent) == 2
    assert recent[0] == str((tmp_path / "c.pdf").resolve())


def test_load_recent_sources_returns_empty_list_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_miner, "RECENT_SOURCES_PATH", tmp_path / "missing.json")

    assert auto_miner.load_recent_sources() == []


def test_prompt_for_source_document_returns_selected_entry():
    result = auto_miner.prompt_for_source_document(
        ["a.pdf", "b.pdf"], input_fn=lambda _: "2"
    )

    assert result == Path("b.pdf")


def test_prompt_for_source_document_reprompts_on_invalid_choice():
    choices = iter(["nope", "9", "1"])

    result = auto_miner.prompt_for_source_document(
        ["a.pdf", "b.pdf"], input_fn=lambda _: next(choices)
    )

    assert result == Path("a.pdf")


def test_prompt_for_source_document_raises_when_no_recent_sources():
    try:
        auto_miner.prompt_for_source_document([], input_fn=lambda _: "1")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


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


def test_fallback_translator_switches_to_offline_after_an_online_failure():
    calls = []
    notices = []

    class OnlineBackend:
        def translate(self, text, source, target):
            calls.append(("online", text, source, target))
            raise RuntimeError("Unexpected status code 429")

    class OfflineBackend:
        def translate(self, text, source, target):
            calls.append(("offline", text, source, target))
            return f"local {text}"

    translator = auto_miner.FallbackTranslator(
        OnlineBackend(),
        OfflineBackend(),
        online_source_code="es",
        online_target_code="en",
        offline_source_code="es",
        offline_target_code="en",
        notify=notices.append,
    )

    assert translator.translate("hola") == "local hola"
    assert translator.translate("adios") == "local adios"
    assert calls == [
        ("online", "hola", "es", "en"),
        ("offline", "hola", "es", "en"),
        ("offline", "adios", "es", "en"),
    ]
    assert len(notices) == 1
    assert "switching to local MarianMT" in notices[0]


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


def test_review_adjusts_context_bounds_without_excluding_the_mined_text():
    added = []
    keys = iter(["start_forward", "start_forward", "start_forward", "end_backward", "enter"])

    auto_miner.review_candidates(
        [_candidate("Uno dos Hola cuatro.")],
        lambda text: text,
        lambda *payload: added.append(payload),
        read_key=lambda: next(keys),
        print_fn=lambda *_: None,
        clear_screen=lambda: None,
    )

    assert added == [("Hola", "Hola", "Hola")]


def test_review_displays_context_outside_the_window_in_gray():
    output = []
    candidate = MiningCandidate(
        "Hola",
        "Hola",
        "Uno Hola tres.",
        "show.srt",
        "00:00:01,000",
    )

    auto_miner.review_candidates(
        [candidate],
        lambda text: text,
        lambda *_: None,
        read_key=iter(["start_forward", "end_backward", "escape"]).__next__,
        print_fn=lambda *values: output.append(" ".join(map(str, values))),
        clear_screen=lambda: None,
    )

    rendered_card = [line for line in output if line.startswith("-")][-1]

    visible_card = auto_miner.ANSI_ESCAPE_PATTERN.sub("", rendered_card)

    assert "| front: Uno [Hola] tres." in visible_card
    assert "\033[90m" in rendered_card
    assert "\033[31m" in rendered_card
    assert "[Hola]\033[0m" in rendered_card
    assert "| back: Hola" in rendered_card


def test_anki_card_preview_has_a_consistent_border_and_wraps_long_text(monkeypatch):
    monkeypatch.setattr(
        auto_miner.shutil,
        "get_terminal_size",
        lambda fallback: os.terminal_size((50, 24)),
    )

    preview = auto_miner.render_anki_card_preview(
        "A sentence with enough words to wrap around the fixed card width.",
        "A translation with enough words to wrap around the fixed card width.",
    )
    lines = preview.splitlines()
    visible_lines = [auto_miner.ANSI_ESCAPE_PATTERN.sub("", line) for line in lines]

    assert visible_lines[0] == visible_lines[-1]
    assert set(visible_lines[0]) == {"-"}
    assert all(len(line) == len(visible_lines[0]) for line in visible_lines)
    assert all(line.startswith("| ") and line.endswith(" |") for line in visible_lines[1:-1])
    assert any("front: A sentence" in line for line in visible_lines)
    assert any("back: A translation" in line for line in visible_lines)


def test_decode_editor_key_resolves_arrow_and_control_sequences():
    keys = iter(["\xe0", "K", "\x00", "M", "\r", "\x08", "\x13", "a"])
    read = lambda: next(keys)

    decoded = [auto_miner._decode_editor_key(read) for _ in range(6)]

    assert decoded == ["left", "right", "enter", "backspace", "save", "a"]


def test_apply_editor_key_inserts_moves_and_splits_lines():
    lines, row, col = auto_miner._apply_editor_key(["ab"], 0, 1, "x")
    assert (lines, row, col) == (["axb"], 0, 2)

    lines, row, col = auto_miner._apply_editor_key(["axb"], 0, 3, "enter")
    assert (lines, row, col) == (["axb", ""], 1, 0)

    lines, row, col = auto_miner._apply_editor_key(["axb", "c"], 1, 0, "backspace")
    assert (lines, row, col) == (["axbc"], 0, 3)

    lines, row, col = auto_miner._apply_editor_key(["axbc"], 0, 4, "left")
    assert (lines, row, col) == (["axbc"], 0, 3)

    lines, row, col = auto_miner._apply_editor_key(["axbc"], 0, 3, "delete")
    assert (lines, row, col) == (["axb"], 0, 3)


def test_apply_editor_key_up_and_down_clamp_column_to_line_length():
    lines, row, col = auto_miner._apply_editor_key(["uno", "do"], 0, 3, "down")
    assert (lines, row, col) == (["uno", "do"], 1, 2)

    lines, row, col = auto_miner._apply_editor_key(["uno", "do"], 1, 2, "up")
    assert (lines, row, col) == (["uno", "do"], 0, 2)


def test_edit_input_file_writes_typed_text_on_save(tmp_path):
    queue = tmp_path / "automine_inputs.txt"
    queue.write_text("uno", encoding="utf-8")
    keys = iter(["end", "enter", "d", "o", "s", "save"])

    auto_miner.edit_input_file(
        queue,
        read_key=lambda: next(keys),
        print_fn=lambda *_: None,
        clear_screen=lambda: None,
        move_cursor=lambda *_: None,
    )

    assert queue.read_text(encoding="utf-8") == "uno\ndos"


def test_edit_input_file_starts_empty_when_queue_file_is_missing(tmp_path):
    queue = tmp_path / "automine_inputs.txt"
    keys = iter(["u", "n", "o", "save"])

    auto_miner.edit_input_file(
        queue,
        read_key=lambda: next(keys),
        print_fn=lambda *_: None,
        clear_screen=lambda: None,
        move_cursor=lambda *_: None,
    )

    assert queue.read_text(encoding="utf-8") == "uno"


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
    monkeypatch.setattr(auto_miner, "start_anki_if_needed", lambda: False)
    monkeypatch.setattr(auto_miner, "test_anki_connection", lambda: True)
    monkeypatch.setattr(auto_miner, "review_candidates", review)
    monkeypatch.setattr(auto_miner.sys, "stdin", InteractiveInput())
    monkeypatch.setattr(auto_miner, "RECENT_SOURCES_PATH", tmp_path / "recent_sources.json")
    monkeypatch.setattr(auto_miner, "edit_input_file", lambda *args, **kwargs: None)

    assert auto_miner.main([str(queue), "source.srt"]) == 0
    assert queue.read_text(encoding="utf-8") == "dos\n"
    assert [call[1]["queue_position"] for call in reviewed] == [1, 2]
    assert all(call[1]["queue_total"] == 2 for call in reviewed)


def test_main_saves_edited_queue_even_when_anki_fails_to_start(tmp_path, monkeypatch):
    import msvcrt

    queue = tmp_path / "automine_inputs.txt"
    queue.write_text("uno", encoding="utf-8")
    keystrokes = iter(["\r", "d", "o", "s", "\x13"])

    class InteractiveInput:
        @staticmethod
        def isatty():
            return True

    def fail_to_start():
        raise FileNotFoundError("Anki is not running and its executable could not be found.")

    monkeypatch.setattr(msvcrt, "getwch", lambda: next(keystrokes))
    monkeypatch.setattr(auto_miner, "load_source_contexts", lambda _: ["context"])
    monkeypatch.setattr(auto_miner, "start_anki_if_needed", fail_to_start)
    monkeypatch.setattr(auto_miner.sys, "stdin", InteractiveInput())

    assert auto_miner.main([str(queue), "source.srt"]) == 1
    assert queue.read_text(encoding="utf-8") == "uno\ndos"


def test_main_prompts_for_source_when_omitted(tmp_path, monkeypatch):
    queue = tmp_path / "automine_inputs.txt"
    queue.write_text("uno\n", encoding="utf-8")
    remembered_path = tmp_path / "picked.srt"

    class InteractiveInput:
        @staticmethod
        def isatty():
            return True

    monkeypatch.setattr(auto_miner, "RECENT_SOURCES_PATH", tmp_path / "recent_sources.json")
    monkeypatch.setattr(auto_miner, "DEFAULT_INPUT_FILE", queue)
    monkeypatch.setattr(auto_miner, "load_recent_sources", lambda: [str(remembered_path)])
    monkeypatch.setattr(auto_miner, "prompt_for_source_document", lambda recent: remembered_path)
    monkeypatch.setattr(auto_miner, "load_source_contexts", lambda path: ["context"] if path == remembered_path else [])
    monkeypatch.setattr(auto_miner, "find_all_candidates", lambda *_: [[_candidate("Uno.")]])
    monkeypatch.setattr(auto_miner, "start_anki_if_needed", lambda: False)
    monkeypatch.setattr(auto_miner, "test_anki_connection", lambda: True)
    monkeypatch.setattr(auto_miner, "review_candidates", lambda *args, **kwargs: True)
    monkeypatch.setattr(auto_miner, "edit_input_file", lambda *args, **kwargs: None)
    monkeypatch.setattr(auto_miner.sys, "stdin", InteractiveInput())
    monkeypatch.chdir(tmp_path)

    assert auto_miner.main([]) == 0
    assert auto_miner.load_recent_sources() == [str(remembered_path.resolve())]
