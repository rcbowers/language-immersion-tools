"""Behavior tests for translation backends. Libraries are faked: no network, no model downloads."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from immersion_app.integrations import translation_backends as tb


@pytest.fixture(autouse=True)
def _clean_thread_locals():
    for name in ("translator", "async_translator", "async_loop"):
        setattr(tb._online_tls, name, None)
    yield
    loop = getattr(tb._online_tls, "async_loop", None)
    if loop is not None and not loop.is_closed():
        loop.close()
    for name in ("translator", "async_translator", "async_loop"):
        setattr(tb._online_tls, name, None)


def _install_googletrans(monkeypatch, translator_cls):
    monkeypatch.setitem(sys.modules, "googletrans", SimpleNamespace(Translator=translator_cls))


# --- online, sync variant ------------------------------------------------


class _SyncTranslator:
    created = 0
    fail = None

    def __init__(self, **kwargs):
        type(self).created += 1

    def translate(self, text, src=None, dest=None):
        if type(self).fail:
            raise type(self).fail
        if isinstance(text, list):
            return [SimpleNamespace(text=f"<{t}>") for t in text]
        return SimpleNamespace(text=f"<{text}>")


@pytest.fixture
def sync_backend(monkeypatch):
    _SyncTranslator.created = 0
    _SyncTranslator.fail = None
    _install_googletrans(monkeypatch, _SyncTranslator)
    backend = tb.OnlineTranslationBackend()
    backend._is_async = False
    return backend


def test_online_translate_extracts_text(sync_backend):
    assert sync_backend.translate("hola", "es", "en") == "<hola>"


def test_online_translator_is_reused_within_a_thread(sync_backend):
    sync_backend.translate("a", "es", "en")
    sync_backend.translate("b", "es", "en")
    assert _SyncTranslator.created == 1


@pytest.mark.parametrize("error", [RuntimeError("HTTP 429 Too Many Requests"), ConnectionError("down")])
def test_online_errors_propagate_and_reset_translator(sync_backend, error):
    sync_backend.translate("ok", "es", "en")
    _SyncTranslator.fail = error
    with pytest.raises(type(error)):
        sync_backend.translate("hola", "es", "en")  # never returns the source text
    assert tb._online_tls.translator is None
    _SyncTranslator.fail = None
    sync_backend.translate("again", "es", "en")
    assert _SyncTranslator.created == 2  # a fresh translator was built after the failure


def test_online_result_without_text_attribute_is_an_error(sync_backend, monkeypatch):
    monkeypatch.setattr(_SyncTranslator, "translate", lambda self, t, src=None, dest=None: object())
    with pytest.raises(RuntimeError, match="Unexpected translation result"):
        sync_backend.translate("hola", "es", "en")


def test_online_batch_preserves_order_and_count(sync_backend):
    assert sync_backend.translate_batch(["a", "b", "c"], "es", "en") == ["<a>", "<b>", "<c>"]
    assert sync_backend.translate_batch([], "es", "en") == []


def test_online_batch_wraps_single_result(sync_backend, monkeypatch):
    monkeypatch.setattr(_SyncTranslator, "translate", lambda self, t, src=None, dest=None: SimpleNamespace(text="one"))
    assert sync_backend.translate_batch(["a"], "es", "en") == ["one"]


def test_online_batch_failure_resets_translator(sync_backend):
    sync_backend.translate("a", "es", "en")
    _SyncTranslator.fail = RuntimeError("429")
    with pytest.raises(RuntimeError):
        sync_backend.translate_batch(["a"], "es", "en")
    assert tb._online_tls.translator is None


def test_online_translate_without_library_raises_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "googletrans", None)  # makes `import googletrans` raise ImportError
    backend = tb.OnlineTranslationBackend()
    with pytest.raises(RuntimeError, match="googletrans library not installed"):
        backend.translate("hola", "es", "en")
    with pytest.raises(RuntimeError, match="googletrans library not installed"):
        backend.translate_batch(["hola"], "es", "en")
    assert backend.is_available() is False
    assert backend.get_name() == "Online"


def test_online_is_available_when_installed(sync_backend):
    assert sync_backend.is_available() is True


# --- online, async variant ------------------------------------------------


class _AsyncTranslator:
    entered = 0
    exited = 0
    fail = None

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        type(self).entered += 1
        return self

    async def __aexit__(self, *exc):
        type(self).exited += 1

    async def translate(self, text, src=None, dest=None):
        if type(self).fail:
            raise type(self).fail
        if isinstance(text, list):
            return [SimpleNamespace(text=f"<{t}>") for t in text]
        return SimpleNamespace(text=f"<{text}>")


@pytest.fixture
def async_backend(monkeypatch):
    _AsyncTranslator.entered = _AsyncTranslator.exited = 0
    _AsyncTranslator.fail = None
    _install_googletrans(monkeypatch, _AsyncTranslator)
    return tb.OnlineTranslationBackend()


def test_async_variant_is_detected(async_backend):
    assert async_backend._is_async_variant() is True


def test_sync_variant_is_detected(monkeypatch):
    _SyncTranslator.fail = None
    _install_googletrans(monkeypatch, _SyncTranslator)
    assert tb.OnlineTranslationBackend()._is_async_variant() is False


def test_async_translate_and_batch(async_backend):
    assert async_backend.translate("hola", "es", "en") == "<hola>"
    assert async_backend.translate_batch(["a", "b"], "es", "en") == ["<a>", "<b>"]
    assert _AsyncTranslator.entered == 1  # persistent per-thread translator, entered once


def test_async_failure_propagates_and_closes_translator(async_backend):
    async_backend.translate("ok", "es", "en")
    _AsyncTranslator.fail = RuntimeError("429")
    with pytest.raises(RuntimeError, match="429"):
        async_backend.translate("hola", "es", "en")
    assert _AsyncTranslator.exited == 1
    assert tb._online_tls.async_translator is None
    _AsyncTranslator.fail = None
    assert async_backend.translate("again", "es", "en") == "<again>"
    assert _AsyncTranslator.entered == 2


def test_async_batch_failure_propagates(async_backend):
    _AsyncTranslator.fail = RuntimeError("boom")
    with pytest.raises(RuntimeError, match="boom"):
        async_backend.translate_batch(["a"], "es", "en")


# --- MarianMT (fake transformers/torch, so this runs without the offline extras) ---


class _FakeTensor:
    def to(self, device):
        return self


class _FakeTokenizer:
    @classmethod
    def from_pretrained(cls, name):
        if name in _FakeMarian.missing:
            raise OSError(f"{name} is not a valid model identifier")
        _FakeMarian.loaded.append(name)
        return cls()

    def __call__(self, texts, **kwargs):
        self.texts = list(texts)
        return {"input_ids": _FakeTensor()}

    def batch_decode(self, tokens, skip_special_tokens=True):
        return [f"<{t}>" for t in self.texts]


class _FakeModel:
    @classmethod
    def from_pretrained(cls, name):
        return cls()

    def to(self, device):
        _FakeMarian.devices.append(device)
        return self

    def eval(self):
        pass

    def generate(self, **kwargs):
        return "tokens"


class _FakeMarian:
    missing: set = set()
    loaded: list = []
    devices: list = []


class _NoGrad:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install_fake_torch(monkeypatch, cuda=False, mps=False):
    torch = types.ModuleType("torch")
    torch.cuda = SimpleNamespace(is_available=lambda: cuda, empty_cache=lambda: None)
    torch.backends = SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps))
    torch.no_grad = lambda: _NoGrad()
    monkeypatch.setitem(sys.modules, "torch", torch)
    transformers = types.ModuleType("transformers")
    transformers.MarianMTModel = _FakeModel
    transformers.MarianTokenizer = _FakeTokenizer
    monkeypatch.setitem(sys.modules, "transformers", transformers)


@pytest.fixture
def marian(monkeypatch):
    _FakeMarian.missing, _FakeMarian.loaded, _FakeMarian.devices = set(), [], []
    _install_fake_torch(monkeypatch)
    return tb.MarianMTTranslationBackend()


@pytest.mark.parametrize(
    "cuda, mps, expected", [(True, False, "cuda"), (False, True, "mps"), (False, False, "cpu"), (True, True, "cuda")]
)
def test_marian_device_selection(monkeypatch, cuda, mps, expected):
    _install_fake_torch(monkeypatch, cuda=cuda, mps=mps)
    assert tb.MarianMTTranslationBackend()._device == expected


def test_marian_device_is_cpu_without_torch(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    assert tb.MarianMTTranslationBackend()._device == "cpu"


def test_marian_model_name(marian):
    assert marian._get_model_name("es", "en") == "Helsinki-NLP/opus-mt-es-en"
    assert marian._get_model_name("jap", "en") == "Helsinki-NLP/opus-mt-jap-en"


def test_marian_translate_and_batch(marian):
    assert marian.translate("hola", "es", "en") == "<hola>"
    assert marian.translate_batch(["a", "b"], "es", "en") == ["<a>", "<b>"]
    assert marian.translate("   ", "es", "en") == ""
    assert marian.translate_batch([], "es", "en") == []


def test_marian_model_is_loaded_once_per_pair(marian):
    marian.translate("a", "es", "en")
    marian.translate("b", "es", "en")
    marian.translate("c", "fr", "en")
    assert _FakeMarian.loaded == ["Helsinki-NLP/opus-mt-es-en", "Helsinki-NLP/opus-mt-fr-en"]


def test_marian_unknown_pair_raises_clear_error(marian):
    _FakeMarian.missing = {"Helsinki-NLP/opus-mt-es-zh"}
    with pytest.raises(RuntimeError, match="opus-mt-es-zh"):
        marian.translate("hola", "es", "zh")


def test_marian_batch_falls_back_to_individual_requests(marian, monkeypatch):
    calls = []

    def fake_with_model(texts, src, dest):
        calls.append(list(texts))
        if len(texts) > 1:
            raise RuntimeError("batch too big")
        return [f"<{texts[0]}>"]

    monkeypatch.setattr(marian, "_translate_with_model", fake_with_model)
    assert marian.translate_batch(["a", "b"], "es", "en") == ["<a>", "<b>"]
    assert calls == [["a", "b"], ["a"], ["b"]]


def test_marian_clear_model_cache(marian):
    marian.translate("a", "es", "en")
    assert marian._models
    marian.clear_model_cache()
    assert marian._models == {} and marian._model_locks == {}
    marian.translate("a", "es", "en")
    assert _FakeMarian.loaded.count("Helsinki-NLP/opus-mt-es-en") == 2  # reloaded after clearing


def test_marian_missing_libraries_give_install_hint(monkeypatch):
    _install_fake_torch(monkeypatch)
    backend = tb.MarianMTTranslationBackend()
    monkeypatch.setitem(sys.modules, "transformers", None)
    with pytest.raises(RuntimeError, match="transformers or torch not installed"):
        backend._get_or_load_model("es", "en")


def test_marian_metadata(marian):
    assert marian.get_name() == "MarianMT"


# --- Argos backend (fake library) ----------------------------------------


def test_argos_translate_requires_library(monkeypatch):
    monkeypatch.setitem(sys.modules, "argostranslate", None)
    monkeypatch.setitem(sys.modules, "argostranslate.package", None)
    monkeypatch.setitem(sys.modules, "argostranslate.translate", None)
    backend = tb.OfflineTranslationBackend()
    with pytest.raises(RuntimeError, match="argostranslate library not installed"):
        backend.translate("hola", "es", "en")
    assert backend.is_available() is False
    assert backend.get_name() == "Offline"
