import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from immersion_app.core.translation_service import TranslationService


class _Pool:
    def __init__(self):
        self.tasks = []

    def start(self, task):
        self.tasks.append(task)


class TranslationServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_cached_translation_emits_immediately(self):
        pool = _Pool()
        service = TranslationService("es", "en", mode="online", thread_pool=pool)
        service.translation_cache[("es", "en", "hola")] = "hello"
        events = []
        service.translation_ready.connect(lambda request_id, text, translation, visible: events.append((request_id, text, translation, visible)))

        request_id = service.translate_async("hola", visible=True)

        self.assertEqual(request_id, 0)
        self.assertEqual(events, [(0, "hola", "hello", True)])
        self.assertEqual(pool.tasks, [])

    def test_visible_request_tracks_and_caches_completion(self):
        pool = _Pool()
        service = TranslationService("es", "en", mode="online", thread_pool=pool)
        service._get_translation_backend = lambda: object()
        service._get_translation_language_codes = lambda: ("es", "en")
        events = []
        service.translation_ready.connect(lambda request_id, text, translation, visible: events.append((request_id, text, translation, visible)))

        request_id = service.translate_async("hola", visible=True)

        self.assertEqual(request_id, 1)
        self.assertEqual(len(pool.tasks), 1)

        service._on_translation_done(1, "hola", "hello", True)

        self.assertEqual(service.translation_cache[("es", "en", "hola")], "hello")
        self.assertEqual(events[-1], (1, "hola", "hello", True))

    def test_prefetch_deduplicates_duplicate_text(self):
        pool = _Pool()
        service = TranslationService("es", "en", mode="offline", thread_pool=pool)
        service._get_translation_backend = lambda: object()
        service._get_translation_language_codes = lambda: ("es", "en")

        service.prefetch_async(["hola", "hola"])

        self.assertEqual(len(pool.tasks), 1)


if __name__ == "__main__":
    unittest.main()
