"""Tests for TranslationService state handling: staleness, upgrades, prefetch, availability."""

from __future__ import annotations

import pytest

from immersion_app.core import translation_service as ts


class _Pool:
    def __init__(self):
        self.tasks = []
        self.cleared = False
        self.waited = None

    def start(self, task):
        self.tasks.append(task)

    def run_all(self):
        tasks, self.tasks = self.tasks, []
        for task in tasks:
            task.run()

    def clear(self):
        self.cleared = True
        self.tasks.clear()

    def waitForDone(self, ms):
        self.waited = ms


class _Backend:
    def __init__(self, fail_on=(), batch=True):
        self.fail_on = set(fail_on)
        self.calls = []
        self.batch_calls = []
        self.cache_cleared = False
        if batch:
            self.translate_batch = self._translate_batch

    def translate(self, text, src, dest):
        self.calls.append((text, src, dest))
        if text in self.fail_on:
            raise RuntimeError(f"cannot translate {text}")
        return f"<{text}>"

    def _translate_batch(self, texts, src, dest):
        self.batch_calls.append((list(texts), src, dest))
        return [f"<{t}>" for t in texts]

    def clear_model_cache(self):
        self.cache_cleared = True


class _Recorder:
    def __init__(self, signal):
        self.calls = []
        signal.connect(lambda *args: self.calls.append(args))


@pytest.fixture
def pools():
    return _Pool(), _Pool()


@pytest.fixture
def service(pools):
    main_pool, prefetch_pool = pools
    service = ts.TranslationService("es", "en", mode="online", thread_pool=main_pool)
    service._prefetch_pool = prefetch_pool
    service._online_backend = _Backend()
    service._offline_backend = _Backend()
    return service


# --- request lifecycle ---------------------------------------------------


def test_empty_text_is_ignored(service, pools):
    assert service.translate_async("") is None
    assert pools[0].tasks == []


def test_visible_request_runs_on_main_pool_and_caches(service, pools):
    ready = _Recorder(service.translation_ready)
    request_id = service.translate_async("hola")
    assert request_id == 1 and len(pools[0].tasks) == 1 and not pools[1].tasks
    pools[0].run_all()
    assert ready.calls == [(1, "hola", "<hola>", True)]
    assert service.cached_translation("hola") == "<hola>"
    assert service._translation_requests == {} and service._translation_requests_by_key == {}


def test_prefetch_request_uses_prefetch_pool(service, pools):
    service.translate_async("hola", visible=False)
    assert len(pools[1].tasks) == 1 and not pools[0].tasks


def test_visible_request_upgrades_inflight_prefetch(service, pools):
    ready = _Recorder(service.translation_ready)
    first = service.translate_async("hola", visible=False)
    second = service.translate_async("hola", visible=True)
    assert first == second
    assert len(pools[1].tasks) == 1 and not pools[0].tasks  # no duplicate task
    pools[1].run_all()
    assert ready.calls == [(first, "hola", "<hola>", True)]  # delivered as visible


def test_prefetch_request_does_not_downgrade_visible(service, pools):
    service.translate_async("hola", visible=True)
    assert service.translate_async("hola", visible=False) == 1
    assert service._translation_requests[1]["visible"] is True


def test_cached_text_emits_immediately_with_id_zero(service, pools):
    service.translation_cache[("es", "en", "hola")] = "hello"
    ready = _Recorder(service.translation_ready)
    assert service.translate_async("hola", visible=False) == 0
    assert ready.calls == [(0, "hola", "hello", False)]
    assert pools[0].tasks == [] and pools[1].tasks == []


def test_uses_google_codes_online_and_marian_codes_offline(service, pools):
    service.set_languages("ja", "zh")
    service._online_backend = _Backend()
    service._offline_backend = _Backend()
    service.translate_async("x")
    assert pools[0].tasks[0].src_lang == "ja" and pools[0].tasks[0].dest_lang == "zh-cn"
    service.set_mode("offline")
    service._offline_backend = _Backend()
    service.translate_async("y")
    assert (pools[0].tasks[1].src_lang, pools[0].tasks[1].dest_lang) == ("jap", "zh")


def test_set_mode_emits(service):
    changed = _Recorder(service.mode_changed)
    service.set_mode("offline")
    assert changed.calls == [("offline",)] and service.translation_mode == "offline"


# --- staleness -----------------------------------------------------------


def test_language_change_drops_late_success(service, pools):
    ready = _Recorder(service.translation_ready)
    service.translate_async("hola")
    task = pools[0].tasks.pop()
    service.set_languages("fr", "en")  # clears cache, bumps context version
    task.run()  # the old result arrives late
    assert ready.calls == []
    assert service.translation_cache == {}
    assert service._translation_requests_by_key == {}  # key freed, not leaked


def test_language_change_drops_late_failure(service, pools):
    service._online_backend = _Backend(fail_on={"hola"})
    failed = _Recorder(service.translation_failed)
    service.translate_async("hola")
    task = pools[0].tasks.pop()
    service.set_languages("fr", "en")
    task.run()
    assert failed.calls == []


def test_set_languages_clears_cache_and_backends(service):
    offline = service._offline_backend
    service.translation_cache[("es", "en", "x")] = "y"
    version = service._translation_context_version
    service.set_languages("it", "en")
    assert service.translation_cache == {}
    assert service._translation_context_version == version + 1
    assert offline.cache_cleared is True
    assert service._online_backend is None and service._offline_backend is None


def test_unknown_request_result_is_ignored(service):
    ready = _Recorder(service.translation_ready)
    failed = _Recorder(service.translation_failed)
    service._on_translation_done(99, "x", "y", True)
    service._on_translation_failed(99, "x", "err", True)
    assert ready.calls == [] and failed.calls == []


# --- failure paths -------------------------------------------------------


def test_failure_carries_visible_flag_and_frees_request(service, pools):
    service._online_backend = _Backend(fail_on={"hola", "adios"})
    failed = _Recorder(service.translation_failed)
    service.translate_async("hola", visible=True)
    service.translate_async("adios", visible=False)
    pools[0].run_all()
    pools[1].run_all()
    assert failed.calls[0] == (1, "hola", "cannot translate hola", True)
    assert failed.calls[1] == (2, "adios", "cannot translate adios", False)
    assert service._translation_requests == {} and service._translation_requests_by_key == {}
    assert service.translation_cache == {}


def test_failed_request_can_be_retried(service, pools):
    service._online_backend = _Backend(fail_on={"hola"})
    service.translate_async("hola")
    pools[0].run_all()
    service._online_backend = _Backend()  # backend recovers
    ready = _Recorder(service.translation_ready)
    new_id = service.translate_async("hola")
    assert new_id == 2  # a genuinely new request, not the dead one
    pools[0].run_all()
    assert ready.calls == [(2, "hola", "<hola>", True)]


# --- prefetch ------------------------------------------------------------


def test_prefetch_disabled_does_nothing(service, pools):
    service.set_prefetch_enabled(False)
    service.prefetch_async(["a", "b"])
    assert pools[0].tasks == [] and pools[1].tasks == []


def test_online_prefetch_uses_single_tasks_on_prefetch_pool(service, pools):
    service.prefetch_async(["a", "b", "a", ""])
    assert [t.text for t in pools[1].tasks] == ["a", "b"]
    assert all(not t.visible for t in pools[1].tasks)
    assert pools[0].tasks == []


def test_prefetch_skips_cached_and_inflight(service, pools):
    service.translation_cache[("es", "en", "cached")] = "x"
    service.translate_async("inflight", visible=False)
    pools[1].tasks.clear()
    service.prefetch_async(["cached", "inflight", "new"])
    assert [t.text for t in pools[1].tasks] == ["new"]


def test_prefetch_with_nothing_to_fetch_starts_no_work(service, pools):
    service.translation_cache[("es", "en", "a")] = "x"
    service.prefetch_async(["a", ""])
    assert pools[0].tasks == [] and pools[1].tasks == []


def test_offline_prefetch_uses_one_batch_task(service, pools):
    service.set_mode("offline")
    batch_ready = _Recorder(service.batch_ready)
    service.prefetch_async(["a", "b"])
    assert len(pools[0].tasks) == 1 and isinstance(pools[0].tasks[0], ts.BatchTranslateTask)
    pools[0].run_all()
    assert batch_ready.calls == [(["a", "b"], ["<a>", "<b>"])]
    assert service.cached_translation("a") == "<a>" and service.cached_translation("b") == "<b>"


def test_batch_count_mismatch_fails_and_caches_nothing(service):
    batch_failed = _Recorder(service.batch_failed)
    batch_ready = _Recorder(service.batch_ready)
    service._on_batch_translation_done(["a", "b"], ["only one"])
    assert batch_failed.calls == [("Batch translation count mismatch.",)]
    assert batch_ready.calls == [] and service.translation_cache == {}


def test_batch_failure_retries_each_text_individually(service, pools):
    batch_failed = _Recorder(service.batch_failed)
    service._on_batch_translation_failed(["a", "b"], "boom")
    assert batch_failed.calls == [("boom",)]
    assert [(t.text, t.visible) for t in pools[1].tasks] == [("a", False), ("b", False)]


def test_batch_failure_end_to_end(service, pools):
    service.set_mode("offline")

    class _BadBatch(_Backend):
        def _translate_batch(self, texts, src, dest):
            raise RuntimeError("batch broke")

    service._offline_backend = _BadBatch()
    service.prefetch_async(["a", "b"])
    pools[0].run_all()
    assert [t.text for t in pools[1].tasks] == ["a", "b"]
    pools[1].run_all()
    assert service.cached_translation("a") == "<a>"


# --- tasks ---------------------------------------------------------------


def test_batch_task_falls_back_to_per_text_translate():
    backend = _Backend(batch=False)
    task = ts.BatchTranslateTask(["a", "b"], "es", "en", backend)
    done = _Recorder(task.signals.finished)
    task.run()
    assert done.calls == [(["a", "b"], ["<a>", "<b>"])]
    assert backend.calls == [("a", "es", "en"), ("b", "es", "en")]


def test_batch_task_failure_emits_failed():
    backend = _Backend(fail_on={"b"}, batch=False)
    task = ts.BatchTranslateTask(["a", "b"], "es", "en", backend)
    failed = _Recorder(task.signals.failed)
    task.run()
    assert failed.calls == [(["a", "b"], "cannot translate b")]


def test_translate_task_success_and_failure():
    ok = ts.TranslateTask(3, "hola", "es", "en", _Backend(), True)
    done = _Recorder(ok.signals.finished)
    ok.run()
    assert done.calls == [(3, "hola", "<hola>", True)]
    bad = ts.TranslateTask(4, "hola", "es", "en", _Backend(fail_on={"hola"}), False)
    failed = _Recorder(bad.signals.failed)
    bad.run()
    assert failed.calls == [(4, "hola", "cannot translate hola", False)]


# --- availability --------------------------------------------------------


def test_availability_probe_exception_becomes_false_for_that_mode():
    def probe(mode):
        if mode == "online":
            raise RuntimeError("no network stack")
        return True

    task = ts.AvailabilityTask(probe=probe)
    done = _Recorder(task.signals.finished)
    task.run()
    assert done.calls == [({"online": False, "offline": True},)]


def test_check_availability_async_updates_state_and_emits(service, pools, monkeypatch):
    monkeypatch.setattr(ts, "probe_mode_available", lambda mode: mode == "offline")
    real_init = ts.AvailabilityTask.__init__

    def init(self, probe=None):  # default arg was bound at import time; force the patched probe
        real_init(self, probe=ts.probe_mode_available)

    monkeypatch.setattr(ts.AvailabilityTask, "__init__", init)
    changed = _Recorder(service.availability_changed)
    assert service.availability == {"online": None, "offline": None}
    service.check_availability_async()
    pools[0].run_all()
    assert service.availability == {"online": False, "offline": True}
    assert changed.calls == [({"online": False, "offline": True},)]


def test_probe_offline_requires_all_packages(monkeypatch):
    present = {"transformers", "torch", "sentencepiece"}
    monkeypatch.setattr(ts.importlib.util, "find_spec", lambda name: object() if name in present else None)
    assert ts.probe_mode_available("offline") is True
    present.discard("sentencepiece")
    assert ts.probe_mode_available("offline") is False
    present.clear()
    assert ts.probe_mode_available("offline") is False


def test_probe_offline_never_imports_torch(monkeypatch):
    import sys

    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setattr(ts.importlib.util, "find_spec", lambda name: object())
    ts.probe_mode_available("offline")
    assert "torch" not in sys.modules


def test_probe_online_false_without_network(monkeypatch):
    def refuse(*a, **k):
        raise OSError("unreachable")

    monkeypatch.setattr(ts.socket, "create_connection", refuse)
    assert ts.probe_mode_available("online") is False


def test_probe_online_checks_backend_when_network_up(monkeypatch):
    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(ts.socket, "create_connection", lambda *a, **k: _Conn())
    monkeypatch.setattr(ts.OnlineTranslationBackend, "is_available", lambda self: True)
    assert ts.probe_mode_available("online") is True
    monkeypatch.setattr(ts.OnlineTranslationBackend, "is_available", lambda self: False)
    assert ts.probe_mode_available("online") is False


# --- shutdown ------------------------------------------------------------


def test_shutdown_disables_prefetch_and_clears_pool(service, pools):
    service.translate_async("queued", visible=False)
    service.shutdown(timeout_ms=123)
    assert service.prefetch_enabled is False
    assert pools[1].cleared is True and pools[1].waited == 123
    service.prefetch_async(["more"])
    assert pools[1].tasks == []


def test_real_prefetch_pool_is_limited_to_two_threads():
    service = ts.TranslationService("es", "en")
    assert service._prefetch_pool.maxThreadCount() == 2
