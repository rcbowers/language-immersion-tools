from __future__ import annotations

from datetime import date, datetime, timedelta

from immersion_app.core.activity_analytics import ActivityAnalyticsManager


class StubAnkiAnalytics:
    def today_count(self):
        return 3

    def total_vocabulary_count(self):
        return 42


def _session(
    *,
    start_time: datetime,
    file_path: str,
    file_type: str,
    active_seconds: int,
    open_seconds: int,
    metadata: dict,
) -> dict:
    return {
        "file_path": file_path,
        "file_type": file_type,
        "start_time": start_time.isoformat(),
        "end_time": (start_time + timedelta(seconds=open_seconds)).isoformat(),
        "duration_seconds": active_seconds,
        "elapsed_seconds": open_seconds,
        "metadata": metadata,
    }


def test_dashboard_groups_daily_activity_and_top_sources():
    today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    user_data = {
        "usage_time": {
            "sessions": [
                _session(
                    start_time=today,
                    file_path="C:\\test\\book.pdf",
                    file_type="pdf",
                    active_seconds=1800,
                    open_seconds=2400,
                    metadata={
                        "source_name": "book.pdf",
                        "start_location": "Page 1",
                        "end_location": "Page 6",
                        "start_page_index": 0,
                        "end_page_index": 5,
                        "pages_advanced": 5,
                    },
                ),
                _session(
                    start_time=today,
                    file_path="C:\\test\\clip.mp4",
                    file_type="video",
                    active_seconds=900,
                    open_seconds=1200,
                    metadata={
                        "source_name": "clip.mp4",
                        "start_location": "00:00:00",
                        "end_location": "00:03:00",
                        "start_position_ms": 0,
                        "end_position_ms": 180000,
                        "minutes_advanced": 3.0,
                    },
                ),
                _session(
                    start_time=yesterday,
                    file_path="C:\\test\\old.pdf",
                    file_type="pdf",
                    active_seconds=600,
                    open_seconds=900,
                    metadata={
                        "source_name": "old.pdf",
                        "start_location": "Page 2",
                        "end_location": "Page 4",
                    },
                ),
            ]
        }
    }

    manager = ActivityAnalyticsManager(user_data, anki_analytics=StubAnkiAnalytics())
    snapshot = manager.get_dashboard_data()

    assert snapshot["summary"]["today_active_seconds"] == 2700
    assert snapshot["summary"]["today_open_seconds"] == 3600
    assert snapshot["summary"]["pdf_pages_advanced"] == 7
    assert snapshot["summary"]["video_minutes_advanced"] == 3.0
    assert snapshot["summary"]["cards_added_today"] == 3
    assert snapshot["summary"]["vocabulary_total"] == 42
    assert snapshot["top_sources"][0]["source_name"] == "book.pdf"
    assert snapshot["daily_activity"][0]["sources"][0]["source_name"] == "book.pdf"


def test_legacy_sessions_mark_partial_history_when_consumption_cannot_be_parsed():
    today = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    user_data = {
        "usage_time": {
            "sessions": [
                _session(
                    start_time=today,
                    file_path="C:\\test\\mystery.mp4",
                    file_type="video",
                    active_seconds=1200,
                    open_seconds=1800,
                    metadata={
                        "source_name": "mystery.mp4",
                        "start_location": "",
                        "end_location": "",
                    },
                )
            ]
        }
    }

    manager = ActivityAnalyticsManager(user_data)
    snapshot = manager.get_dashboard_data()

    day = snapshot["daily_activity"][0]
    assert day["active_seconds"] == 1200
    assert day["minutes_advanced"] == 0.0
    assert day["sources"][0]["consumption_is_partial"] is True


def test_streaks_count_only_days_with_activity():
    base_day = datetime.combine(date.today(), datetime.min.time()).replace(hour=8)
    user_data = {
        "usage_time": {
            "sessions": [
                _session(
                    start_time=base_day,
                    file_path="a.pdf",
                    file_type="pdf",
                    active_seconds=300,
                    open_seconds=300,
                    metadata={"source_name": "a.pdf", "start_location": "Page 1", "end_location": "Page 2"},
                ),
                _session(
                    start_time=base_day - timedelta(days=1),
                    file_path="b.pdf",
                    file_type="pdf",
                    active_seconds=300,
                    open_seconds=300,
                    metadata={"source_name": "b.pdf", "start_location": "Page 1", "end_location": "Page 2"},
                ),
                _session(
                    start_time=base_day - timedelta(days=3),
                    file_path="c.pdf",
                    file_type="pdf",
                    active_seconds=300,
                    open_seconds=300,
                    metadata={"source_name": "c.pdf", "start_location": "Page 1", "end_location": "Page 2"},
                ),
            ]
        }
    }

    manager = ActivityAnalyticsManager(user_data)
    snapshot = manager.get_dashboard_data()

    assert snapshot["summary"]["current_streak_days"] == 2
    assert snapshot["summary"]["best_streak_days"] == 2
