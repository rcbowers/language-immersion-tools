"""State manager for LinguaLoop-managed Anki analytics."""

from __future__ import annotations

import re
from datetime import date, datetime

from PySide6.QtCore import QObject, Signal

from immersion_app.core.user_data import save_user_data


class AnkiAnalyticsManager(QObject):
    """Owns persisted Anki add analytics and derived stats."""

    stats_changed = Signal(int, int)  # (today_count, total_vocabulary_count)

    def __init__(self, user_data: dict, snapshot_words: set[str] | None = None):
        super().__init__()
        self._user_data = user_data
        analytics = self._ensure_analytics()
        self._persisted_vocabulary = {
            token.lower()
            for token in analytics.get("vocabulary_seen", [])
            if isinstance(token, str) and token.strip()
        }
        self._snapshot_vocabulary = {
            token.lower()
            for token in (snapshot_words or set())
            if isinstance(token, str) and token.strip()
        }

    def _ensure_analytics(self) -> dict:
        analytics = self._user_data.setdefault("analytics", {})
        analytics["cards_added_total"] = int(analytics.get("cards_added_total") or 0)
        vocabulary = analytics.get("vocabulary_seen")
        analytics["vocabulary_seen"] = vocabulary if isinstance(vocabulary, list) else []
        daily_counts = analytics.get("cards_added_by_day")
        analytics["cards_added_by_day"] = daily_counts if isinstance(daily_counts, dict) else {}
        return analytics

    @property
    def vocabulary_seen(self) -> set[str]:
        return self._persisted_vocabulary | self._snapshot_vocabulary

    def total_cards_added(self) -> int:
        return int(self._user_data["analytics"].get("cards_added_total") or 0)

    def total_vocabulary_count(self) -> int:
        return len(self.vocabulary_seen)

    def today_count(self, target_date: date | None = None) -> int:
        day_key = (target_date or date.today()).isoformat()
        return int(self._user_data["analytics"]["cards_added_by_day"].get(day_key) or 0)

    def set_snapshot_words(self, words: set[str] | list[str]) -> None:
        self._snapshot_vocabulary = {
            token.lower()
            for token in words
            if isinstance(token, str) and token.strip()
        }
        self.stats_changed.emit(self.today_count(), self.total_vocabulary_count())

    def record_successful_card_add(self, word_text: str, added_at: datetime | None = None) -> None:
        analytics = self._user_data["analytics"]
        analytics["cards_added_total"] = self.total_cards_added() + 1

        for token in re.findall(r"\b\w+\b", word_text, flags=re.UNICODE):
            self._persisted_vocabulary.add(token.lower())
        analytics["vocabulary_seen"] = sorted(self._persisted_vocabulary)

        added_on = (added_at or datetime.now()).date().isoformat()
        daily_counts = analytics["cards_added_by_day"]
        daily_counts[added_on] = int(daily_counts.get(added_on) or 0) + 1

        save_user_data(self._user_data)
        self.stats_changed.emit(self.today_count(), self.total_vocabulary_count())
