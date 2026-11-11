"""Tests for AnkiService async add, queue processing and status handling.

Tasks are run synchronously (``task.run()``) and the pool is a fake, so nothing
touches a real thread pool, Anki or the user's queue file.
"""

from __future__ import annotations

import pytest

from immersion_app.core import anki_service as svc
from immersion_app.core.anki import AnkiSetupStatus


class _Pool:
    def __init__(self):
        self.tasks = []

    def start(self, task):
        self.tasks.append(task)

    def run_all(self):
        tasks, self.tasks = self.tasks, []
        for task in tasks:
            task.run()


class _Recorder:
    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *args: self.calls.append(args))


@pytest.fixture
def pool():
    return _Pool()


@pytest.fixture
def service(pool):
    return svc.AnkiService(thread_pool=pool)


@pytest.fixture
def queue_io(monkeypatch):
    """Replace queue persistence with an in-memory fake."""
    state = {"queue": [], "log": [], "saved": []}
    monkeypatch.setattr(svc, "append_queue_entry", lambda entry: state["queue"].append(entry))
    monkeypatch.setattr(svc, "load_queue_entries", lambda: list(state["queue"]))

    def save(entries):
        state["queue"] = list(entries)
        state["saved"].append(list(entries))

    monkeypatch.setattr(svc, "save_queue_entries", save)
    monkeypatch.setattr(svc, "append_processed_log", lambda entries: state["log"].append(list(entries)))
    return state


def _entry(word, sentence="Una frase.", translation="t"):
    return {"word": word, "sentence": sentence, "translation": translation}


# --- AnkiAddTask ---------------------------------------------------------


def test_add_task_success_emits_finished_with_note_id(monkeypatch):
    monkeypatch.setattr(svc, "add_anki_card", lambda s, w, t: 99)
    task = svc.AnkiAddTask({"sentence": "s", "word": "w", "translation": "t", "location": "p1"})
    finished, failed = _Recorder(task.signals.finished), _Recorder(task.signals.failed)
    task.run()
    assert failed.calls == []
    assert finished.calls[0][0] == {"sentence": "s", "word": "w", "translation": "t", "location": "p1", "note_id": 99}


def test_add_task_duplicate_is_not_a_connection_error(monkeypatch):
    def dup(*a):
        raise RuntimeError("AnkiConnect error: duplicate")

    monkeypatch.setattr(svc, "add_anki_card", dup)
    task = svc.AnkiAddTask({"sentence": "s", "word": "w", "translation": "t"})
    failed = _Recorder(task.signals.failed)
    task.run()
    payload, message, is_conn = failed.calls[0]
    assert "duplicate" in message and is_conn is False
    assert payload["word"] == "w"


def test_add_task_connection_error_flagged(monkeypatch):
    def down(*a):
        raise ConnectionError("Anki closed")

    monkeypatch.setattr(svc, "add_anki_card", down)
    task = svc.AnkiAddTask({"sentence": "s", "word": "w", "translation": "t"})
    failed = _Recorder(task.signals.failed)
    task.run()
    assert failed.calls[0][2] is True


# --- AnkiService add -----------------------------------------------------


def test_add_card_async_success_emits_card_added(service, pool, monkeypatch):
    monkeypatch.setattr(svc, "add_anki_card", lambda s, w, t: 5)
    added = _Recorder(service.card_added)
    service.add_card_async("sent", "word", "trans", location="Page 2")
    pool.run_all()
    assert added.calls[0][0]["note_id"] == 5
    assert added.calls[0][0]["location"] == "Page 2"


def test_connection_failure_flips_is_connected_and_emits_both_signals(service, pool, monkeypatch):
    service._is_connected = True

    def down(*a):
        raise ConnectionError("nope")

    monkeypatch.setattr(svc, "add_anki_card", down)
    add_failed, card_failed = _Recorder(service.card_add_failed), _Recorder(service.card_failed)
    service.add_card_async("s", "w", "t")
    pool.run_all()
    assert service.is_connected is False
    assert add_failed.calls[0][2] is True
    assert card_failed.calls == [("nope",)]


def test_duplicate_failure_keeps_connection_state(service, pool, monkeypatch):
    service._is_connected = True

    def dup(*a):
        raise RuntimeError("AnkiConnect error: duplicate")

    monkeypatch.setattr(svc, "add_anki_card", dup)
    add_failed, card_failed = _Recorder(service.card_add_failed), _Recorder(service.card_failed)
    service.add_card_async("s", "w", "t")
    pool.run_all()
    assert service.is_connected is True
    assert add_failed.calls and card_failed.calls
    assert "duplicate" in card_failed.calls[0][0]


def test_add_card_now_emits_and_returns_note_id(service, monkeypatch):
    monkeypatch.setattr(svc, "add_anki_card", lambda s, w, t: 11)
    added = _Recorder(service.card_added)
    assert service.add_card_now("s", "w", "t") == 11
    assert added.calls[0][0] == {"sentence": "s", "word": "w", "translation": "t", "note_id": 11}


# --- QueueProcessTask ----------------------------------------------------


def test_queue_task_numbers_repeated_sentences(monkeypatch):
    sent = []
    monkeypatch.setattr(svc, "add_anki_card", lambda s, w, t: sent.append((s, w)))
    entries = [_entry("a", "Same."), _entry("b", "Same."), _entry("c", "Same."), _entry("d", "Other.")]
    task = svc.QueueProcessTask(entries)
    finished = _Recorder(task.signals.finished)
    task.run()
    assert sent == [("Same.", "a"), ("Same. (2)", "b"), ("Same. (3)", "c"), ("Other.", "d")]
    assert finished.calls[0][0] == entries and finished.calls[0][1] == []


def test_queue_task_failures_are_collected_and_rest_still_run(monkeypatch):
    def add(sentence, word, translation):
        if word == "bad":
            raise RuntimeError("duplicate")

    monkeypatch.setattr(svc, "add_anki_card", add)
    entries = [_entry("ok1"), _entry("bad"), _entry("ok2")]
    task = svc.QueueProcessTask(entries)
    finished = _Recorder(task.signals.finished)
    task.run()
    ok, failed = finished.calls[0]
    assert [e["word"] for e in ok] == ["ok1", "ok2"]
    assert [e["word"] for e in failed] == ["bad"]


def test_queue_task_unexpected_error_emits_failed(monkeypatch):
    monkeypatch.setattr(svc, "add_anki_card", lambda *a: None)
    task = svc.QueueProcessTask([{"word": "x"}])  # missing 'sentence' -> KeyError outside per-entry handling
    failed = _Recorder(task.signals.failed)
    task.run()
    assert failed.calls


# --- queue finalisation --------------------------------------------------


def test_finalize_keeps_only_failed_entries_and_logs_successes(service, queue_io):
    ok, bad = [_entry("ok")], [_entry("bad")]
    processed, entries_signal = _Recorder(service.queue_processed), _Recorder(service.queue_entries_processed)
    service._finalize_queue_processing(ok, bad)
    assert queue_io["queue"] == bad
    assert queue_io["log"] == [ok]
    assert entries_signal.calls == [(ok, bad)]
    count_ok, count_bad, path = processed.calls[0]
    assert (count_ok, count_bad) == (1, 1)
    assert path.endswith("processed_cards.log")


def test_finalize_with_no_successes_does_not_write_log(service, queue_io):
    service._finalize_queue_processing([], [_entry("bad")])
    assert queue_io["log"] == []
    assert queue_io["queue"] == [_entry("bad")]


def test_finalize_all_success_empties_queue(service, queue_io):
    service._finalize_queue_processing([_entry("a")], [])
    assert queue_io["queue"] == []


def test_process_queue_async_end_to_end(service, pool, queue_io, monkeypatch):
    def add(sentence, word, translation):
        if word == "bad":
            raise ConnectionError("down")

    monkeypatch.setattr(svc, "add_anki_card", add)
    queue_io["queue"] = [_entry("ok"), _entry("bad")]
    processed = _Recorder(service.queue_processed)
    service.process_queue_async()
    pool.run_all()
    assert [e["word"] for e in queue_io["queue"]] == ["bad"]
    assert processed.calls[0][:2] == (1, 1)


def test_process_queue_now_matches_async_split(service, queue_io, monkeypatch):
    sent = []

    def add(sentence, word, translation):
        sent.append(sentence)
        if word == "bad":
            raise RuntimeError("duplicate")

    monkeypatch.setattr(svc, "add_anki_card", add)
    queue_io["queue"] = [_entry("ok", "S."), _entry("bad", "S."), _entry("ok2", "S.")]
    ok, failed = service.process_queue_now()
    assert [e["word"] for e in ok] == ["ok", "ok2"]
    assert [e["word"] for e in failed] == ["bad"]
    assert sent == ["S.", "S. (2)", "S. (3)"]
    assert [e["word"] for e in queue_io["queue"]] == ["bad"]
    assert queue_io["log"] and [e["word"] for e in queue_io["log"][0]] == ["ok", "ok2"]


# --- status handling -----------------------------------------------------


def test_status_finished_sets_status_and_emits_vocabulary(service):
    service._request_id = 3
    status = AnkiSetupStatus(connected=True, deck_exists=True, note_type_exists=True, message="Ready")
    conn, setup, vocab = (_Recorder(service.connection_changed), _Recorder(service.setup_status_changed),
                          _Recorder(service.vocabulary_loaded))
    service._on_status_finished(3, True, {"gato"}, status)
    assert service.is_connected and service.setup_status is status
    assert conn.calls == [(True,)] and setup.calls == [(status,)] and vocab.calls == [({"gato"},)]


def test_status_finished_builds_fallback_status_and_skips_none_words(service):
    service._request_id = 1
    vocab = _Recorder(service.vocabulary_loaded)
    service._on_status_finished(1, False, None, None)
    assert service.setup_status.connected is False
    assert service.setup_status.message == ""
    assert vocab.calls == []
    service._request_id = 2
    service._on_status_finished(2, True, set(), "not a status")
    assert service.setup_status.message == "Ready" and service.setup_status.ok
    assert vocab.calls == [(set(),)]  # empty set is a real (empty) deck, still emitted


def test_status_failed_marks_disconnected(service):
    service._request_id = 4
    service._is_connected = True
    setup, conn = _Recorder(service.setup_status_changed), _Recorder(service.connection_changed)
    service._on_status_failed(4, "timeout")
    assert service.is_connected is False
    assert setup.calls[0][0].message == "timeout"
    assert conn.calls == [(False,)]


def test_stale_status_failure_is_ignored(service):
    service._request_id = 5
    service._is_connected = True
    service._on_status_failed(4, "old")
    assert service.is_connected is True and service.setup_status is None


def test_status_task_emits_finished_with_words_only_when_ok(monkeypatch):
    ok = AnkiSetupStatus(connected=True, deck_exists=True, note_type_exists=True, message="Ready")
    monkeypatch.setattr(svc, "check_anki_setup", lambda: ok)
    monkeypatch.setattr(svc, "fetch_deck_words", lambda: {"w"})
    task = svc.AnkiStatusTask(1)
    finished = _Recorder(task.signals.finished)
    task.run()
    assert finished.calls[0][:3] == (1, True, {"w"})

    bad = AnkiSetupStatus(connected=True, message="deck missing")
    monkeypatch.setattr(svc, "check_anki_setup", lambda: bad)
    monkeypatch.setattr(svc, "fetch_deck_words", lambda: pytest.fail("must not fetch words when not ready"))
    task = svc.AnkiStatusTask(2)
    finished = _Recorder(task.signals.finished)
    task.run()
    assert finished.calls[0][1] is False and finished.calls[0][2] is None


def test_status_task_exception_emits_failed(monkeypatch):
    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(svc, "check_anki_setup", boom)
    task = svc.AnkiStatusTask(7)
    failed = _Recorder(task.signals.failed)
    task.run()
    assert failed.calls == [(7, "kaboom")]


# --- queueing ------------------------------------------------------------


def test_queue_card_persists_then_emits(service, queue_io):
    order = []
    service.queue_entry_added.connect(lambda p: order.append(("emit", len(queue_io["queue"]))))
    payload = service.build_queue_payload(word="w", sentence="s", translation="t", source_name="b.pdf",
                                          source_type="pdf", location="Page 1")
    service.queue_card(payload)
    assert queue_io["queue"] == [payload]
    assert order == [("emit", 1)]  # already persisted when the signal fired


def test_build_queue_payload_defaults(service):
    payload = service.build_queue_payload(word="gato", sentence="", translation="cat", source_name="n",
                                          source_type="video", location="0:10")
    assert payload["sentence"] == "gato"
    assert payload["status"] == "queued"
    assert payload["created_at"]
    assert payload["source_type"] == "video"


def test_refresh_connection_bumps_request_id_and_starts_task(service, pool):
    started = _Recorder(service.status_check_started)
    service.refresh_connection()
    service.refresh_connection()
    assert started.calls == [(1,), (2,)]
    assert len(pool.tasks) == 2
