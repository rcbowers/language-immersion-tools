"""Unit tests for Anki analytics state management."""

from datetime import datetime
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject

from immersion_app.core.anki_analytics import AnkiAnalyticsManager
from immersion_app.core.user_data import default_user_data


class SignalCapture(QObject):
    """Collect stats change emissions for assertions."""

    def __init__(self):
        super().__init__()
        self.events = []

    def on_stats_changed(self, today_count, total_count):
        self.events.append((today_count, total_count))


class AnkiAnalyticsManagerTests(unittest.TestCase):
    def test_missing_daily_history_defaults_to_empty(self):
        user_data = default_user_data()
        user_data["analytics"].pop("cards_added_by_day", None)

        manager = AnkiAnalyticsManager(user_data)

        self.assertEqual(manager.today_count(datetime(2026, 5, 11).date()), 0)
        self.assertEqual(user_data["analytics"]["cards_added_by_day"], {})

    def test_record_successful_card_add_updates_counts_and_vocabulary(self):
        user_data = default_user_data()
        manager = AnkiAnalyticsManager(user_data, snapshot_words={"adios"}, today=lambda: datetime(2026, 5, 11).date())
        capture = SignalCapture()
        manager.stats_changed.connect(capture.on_stats_changed)

        with patch("immersion_app.core.anki_analytics.save_user_data") as save_user_data:
            manager.record_successful_card_add("Hola mundo", added_at=datetime(2026, 5, 11, 9, 30))

        self.assertEqual(user_data["analytics"]["cards_added_total"], 1)
        self.assertEqual(user_data["analytics"]["cards_added_by_day"]["2026-05-11"], 1)
        self.assertEqual(manager.today_count(datetime(2026, 5, 11).date()), 1)
        self.assertEqual(manager.total_vocabulary_count(), 3)
        self.assertEqual(user_data["analytics"]["vocabulary_seen"], ["hola", "mundo"])
        self.assertEqual(capture.events, [(1, 3)])
        save_user_data.assert_called_once_with(user_data)

    def test_record_successful_card_add_separates_days(self):
        user_data = default_user_data()
        manager = AnkiAnalyticsManager(user_data)

        with patch("immersion_app.core.anki_analytics.save_user_data"):
            manager.record_successful_card_add("hola", added_at=datetime(2026, 5, 11, 9, 30))
            manager.record_successful_card_add("adios", added_at=datetime(2026, 5, 12, 7, 45))

        self.assertEqual(manager.today_count(datetime(2026, 5, 11).date()), 1)
        self.assertEqual(manager.today_count(datetime(2026, 5, 12).date()), 1)
        self.assertEqual(user_data["analytics"]["cards_added_total"], 2)


if __name__ == "__main__":
    unittest.main()
