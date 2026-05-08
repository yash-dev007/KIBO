import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from src.api.event_bus import EventBus
from src.system.notification_router import NotificationRouter
from src.core.config_manager import DEFAULT_CONFIG


@pytest.fixture
def bus():
    return EventBus()


def test_notification_router(tmp_path, monkeypatch, bus):
    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = True
    config["quiet_hours_start"] = 22
    config["quiet_hours_end"] = 7
    config["notification_types"] = {
        "morning-greeting": True,
        "cpu-panic": True
    }

    monkeypatch.setattr("src.system.notification_router.get_user_data_dir", lambda: tmp_path)

    class MockDatetime(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 4, 11, 12, 0, 0)
    monkeypatch.setattr("src.system.notification_router.datetime.datetime", MockDatetime)

    router = NotificationRouter(config, event_bus=bus)

    approved = []
    bus.on("notification_approved", lambda msg, nt: approved.append((msg, nt)))

    res = router.route("morning-greeting", "Good morning!", "low")
    assert res is True
    assert len(approved) == 1

    res = router.route("morning-greeting", "Good morning again!", "low")
    assert res is False
    assert len(approved) == 1

    res = router.route("cpu-panic", "Panic!", "medium")
    assert res is True
    assert len(approved) == 2


def test_quiet_hours(tmp_path, monkeypatch, bus):
    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = True
    config["quiet_hours_start"] = 22
    config["quiet_hours_end"] = 7
    config["notification_types"] = {
        "morning-greeting": True,
        "meeting-reminder": True
    }

    monkeypatch.setattr("src.system.notification_router.get_user_data_dir", lambda: tmp_path)

    class MockDatetimeQuiet(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 4, 11, 23, 0, 0)
    monkeypatch.setattr("src.system.notification_router.datetime.datetime", MockDatetimeQuiet)

    router = NotificationRouter(config, event_bus=bus)

    assert not router.route("morning-greeting", "Hello", "low")
    assert router.route("meeting-reminder", "Meeting!", "high")
