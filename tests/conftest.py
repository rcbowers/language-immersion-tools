"""Shared pytest setup.

* Puts ``src/`` on ``sys.path`` so ``pytest`` works without ``PYTHONPATH``.
* Points the app's data folder at a throwaway directory *before* any
  ``immersion_app`` module is imported, so tests never touch real user data.
* Defaults Qt to the offscreen platform so tests run headless (CI).
* Fails any test that tries to open a non-loopback network connection.
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (str(SRC), str(ROOT), str(ROOT / "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("IMMERSION_DATA_DIR", tempfile.mkdtemp(prefix="immersion-tests-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _is_loopback(address) -> bool:
    if isinstance(address, tuple) and address:
        return str(address[0]) in _LOOPBACK_HOSTS
    return not isinstance(address, tuple)  # AF_UNIX paths and similar


def _guard(real):
    def guarded(self, address, *args, **kwargs):
        if not _is_loopback(address):
            raise RuntimeError(f"Test tried to open a real network connection to {address!r}; mock it instead.")
        return real(self, address, *args, **kwargs)

    return guarded


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch):
    """Tests stay offline: no real Google, AnkiConnect-over-LAN or model downloads.

    Loopback stays allowed because asyncio's Windows event loop uses it internally.
    """
    monkeypatch.setattr(socket.socket, "connect", _guard(_real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _guard(_real_connect_ex))

