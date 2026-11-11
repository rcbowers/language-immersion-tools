"""PdfRenderCache: LRU eviction by entry count and by total bytes."""

from immersion_app.core.pdf_render_cache import PdfRenderCache
from immersion_app.core.pdf_service import PdfRenderResult


def _result(page, size=100):
    return PdfRenderResult(
        page_index=page, page_count=10, width=10, height=10, stride=30, samples=b"x" * size,
        words=[], word_order=[], line_map={},
    )


def _key(page, zoom=2.0, dark=False):
    return PdfRenderCache.make_key("a.pdf", page, zoom, dark)


def test_get_returns_stored_result_and_misses_other_keys():
    cache = PdfRenderCache()
    cache.put(_key(1), _result(1))
    assert cache.get(_key(1)).page_index == 1
    assert cache.get(_key(2)) is None
    assert cache.get(_key(1, dark=True)) is None
    assert cache.get(_key(1, zoom=2.25)) is None


def test_key_rounds_float_noise_in_zoom():
    assert _key(1, zoom=2.0) == _key(1, zoom=2.0000001)


def test_evicts_least_recently_used_by_entry_count():
    cache = PdfRenderCache(max_entries=2)
    cache.put(_key(1), _result(1))
    cache.put(_key(2), _result(2))
    cache.get(_key(1))  # page 1 is now most recent
    cache.put(_key(3), _result(3))
    assert _key(2) not in cache
    assert _key(1) in cache and _key(3) in cache


def test_evicts_by_total_bytes_but_always_keeps_newest():
    cache = PdfRenderCache(max_entries=10, max_bytes=250)
    for page in range(1, 4):
        cache.put(_key(page), _result(page, size=100))
    assert len(cache) == 2 and cache.total_bytes == 200
    cache.put(_key(9), _result(9, size=1000))  # larger than the cap on its own
    assert len(cache) == 1 and _key(9) in cache


def test_put_same_key_replaces_without_double_counting():
    cache = PdfRenderCache()
    cache.put(_key(1), _result(1, size=100))
    cache.put(_key(1), _result(1, size=40))
    assert len(cache) == 1 and cache.total_bytes == 40


def test_clear_empties_cache():
    cache = PdfRenderCache()
    cache.put(_key(1), _result(1))
    cache.clear()
    assert len(cache) == 0 and cache.total_bytes == 0
