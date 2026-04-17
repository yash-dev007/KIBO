import pytest
from datetime import datetime, timedelta
from src.system.notification_router import NotificationRouter
from src.core.config_manager import DEFAULT_CONFIG

def test_notification_router(tmp_path, monkeypatch):
    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = True
    config["quiet_hours_start"] = 22
    config["quiet_hours_end"] = 7
    config["notification_types"] = {
        "morning-greeting": True,
        "cpu-panic": True
    }
    
    monkeypatch.setattr("notification_router.get_user_data_dir", lambda: tmp_path)
    
    # Mock time to be inside non-quiet hours (e.g. 12:00)
    class MockDatetime(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 4, 11, 12, 0, 0)
    monkeypatch.setattr("notification_router.datetime.datetime", MockDatetime)
    
    router = NotificationRouter(config)
    
    approved = []
    router.notification_approved.connect(lambda msg, nt: approved.append((msg, nt)))
    
    # First route should succeed
    res = router.route("morning-greeting", "Good morning!", "low")
    assert res is True
    assert len(approved) == 1
    
    # Second route (cooldown active) should fail
    res = router.route("morning-greeting", "Good morning again!", "low")
    assert res is False
    assert len(approved) == 1
    
    # cpu-panic should bypass quiet hours anyway, but here it's not quiet hours
    res = router.route("cpu-panic", "Panic!", "medium")
    assert res is True
    assert len(approved) == 2

def test_quiet_hours(tmp_path, monkeypatch):
    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = True
    config["quiet_hours_start"] = 22
    config["quiet_hours_end"] = 7
    config["notification_types"] = {
        "morning-greeting": True,
        "meeting-reminder": True
    }
    
    monkeypatch.setattr("notification_router.get_user_data_dir", lambda: tmp_path)
    
    class MockDatetimeQuiet(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 4, 11, 23, 0, 0)
    monkeypatch.setattr("notification_router.datetime.datetime", MockDatetimeQuiet)
    
    router = NotificationRouter(config)
    
    # Low priority blocked by quiet hours
    assert not router.route("morning-greeting", "Hello", "low")
    
    # High priority bypasses quiet hours
    assert router.route("meeting-reminder", "Meeting!", "high")
