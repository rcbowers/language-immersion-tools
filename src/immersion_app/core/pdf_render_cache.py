"""Small LRU cache of rendered PDF pages."""

from __future__ import annotations

from collections import OrderedDict
from typing import Hashable

from immersion_app.core.pdf_service import PdfRenderResult

DEFAULT_MAX_ENTRIES = 6
DEFAULT_MAX_BYTES = 96 * 1024 * 1024


class PdfRenderCache:
    """LRU cache keyed by (path, page, zoom, dark), bounded by entry count and total bytes."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES, max_bytes: int = DEFAULT_MAX_BYTES):
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._items: "OrderedDict[Hashable, PdfRenderResult]" = OrderedDict()
        self._total_bytes = 0

    @staticmethod
    def make_key(path: str, page_index: int, zoom_factor: float, dark: bool) -> tuple:
        return (path, int(page_index), round(float(zoom_factor), 3), bool(dark))

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key) -> bool:
        return key in self._items

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    def get(self, key) -> PdfRenderResult | None:
        result = self._items.get(key)
        if result is not None:
            self._items.move_to_end(key)
        return result

    def put(self, key, result: PdfRenderResult) -> None:
        old = self._items.pop(key, None)
        if old is not None:
            self._total_bytes -= old.nbytes
        self._items[key] = result
        self._total_bytes += result.nbytes
        # Always keep the newest entry, even if it alone exceeds the byte cap.
        while len(self._items) > 1 and (len(self._items) > self.max_entries or self._total_bytes > self.max_bytes):
            _, evicted = self._items.popitem(last=False)
            self._total_bytes -= evicted.nbytes

    def clear(self) -> None:
        self._items.clear()
        self._total_bytes = 0
