import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from immersion_app.integrations import translation_backends
from immersion_app.integrations.translation_backends import OnlineTranslationBackend


def test_online_backend_configures_googletrans_to_raise_on_http_errors(monkeypatch):
    created_with = []

    class Translator:
        def __init__(self, **kwargs):
            created_with.append(kwargs)

    monkeypatch.setitem(sys.modules, "googletrans", SimpleNamespace(Translator=Translator))
    monkeypatch.setattr(translation_backends._online_tls, "translator", None, raising=False)
    backend = OnlineTranslationBackend()

    backend._get_translator()

    assert created_with[0]["raise_exception"] is True
