import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from immersion_app.core.anki_service import AnkiService


class _Pool:
    def __init__(self):
        self.tasks = []

    def start(self, task):
        self.tasks.append(task)


class AnkiServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_refresh_success_emits_connection_and_vocabulary(self):
        pool = _Pool()
        service = AnkiService(thread_pool=pool)
        connection_events = []
        vocabulary_events = []
        started_events = []

        service.status_check_started.connect(started_events.append)
        service.connection_changed.connect(connection_events.append)
        service.vocabulary_loaded.connect(vocabulary_events.append)

        service.refresh_connection()
        self.assertEqual(started_events, [1])
        self.assertEqual(len(pool.tasks), 1)

        service._on_status_finished(1, True, {"hola", "adios"})

        self.assertTrue(service.is_connected)
        self.assertEqual(connection_events, [True])
        self.assertEqual(vocabulary_events, [{"hola", "adios"}])

    def test_refresh_failure_marks_service_disconnected(self):
        pool = _Pool()
        service = AnkiService(thread_pool=pool)
        connection_events = []
        service.connection_changed.connect(connection_events.append)

        service.refresh_connection()
        service._on_status_failed(1, "offline")

        self.assertFalse(service.is_connected)
        self.assertEqual(connection_events, [False])

    def test_stale_refresh_result_is_ignored(self):
        pool = _Pool()
        service = AnkiService(thread_pool=pool)
        connection_events = []
        vocabulary_events = []
        service.connection_changed.connect(connection_events.append)
        service.vocabulary_loaded.connect(vocabulary_events.append)

        service.refresh_connection()
        service.refresh_connection()
        self.assertEqual(len(pool.tasks), 2)

        service._on_status_finished(1, True, {"stale"})
        service._on_status_finished(2, False, None)

        self.assertFalse(service.is_connected)
        self.assertEqual(connection_events, [False])
        self.assertEqual(vocabulary_events, [])


if __name__ == "__main__":
    unittest.main()
