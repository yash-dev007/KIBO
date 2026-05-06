import dataclasses
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
    
    monkeypatch.setattr("src.system.notification_router.get_user_data_dir", lambda: tmp_path)
    
    # Mock time to be inside non-quiet hours (e.g. 12:00)
    class MockDatetime(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 4, 11, 12, 0, 0)
    monkeypatch.setattr("src.system.notification_router.datetime.datetime", MockDatetime)
    
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
    
    router._state = dataclasses.replace(router._state, last_utterance_ts=0)
    # cpu-panic is not quiet-hours blocked here and no longer has a recent global interval.
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

    monkeypatch.setattr("src.system.notification_router.get_user_data_dir", lambda: tmp_path)

    class MockDatetimeQuiet(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 4, 11, 23, 0, 0)
    monkeypatch.setattr("src.system.notification_router.datetime.datetime", MockDatetimeQuiet)

    router = NotificationRouter(config)

    # Low priority blocked by quiet hours
    assert not router.route("morning-greeting", "Hello", "low")

    # Non-explicit high priority still respects quiet hours
    assert not router.route("meeting-reminder", "Meeting!", "high")
    # Explicit user reminders may bypass quiet hours when marked urgent
    assert router.route("reminder", "Reminder!", "high", explicit_reminder=True, bypass_cap=True)


def _make_router(tmp_path, monkeypatch, hour: int = 12, config_overrides: dict = None):
    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = True
    config["quiet_hours_start"] = 22
    config["quiet_hours_end"] = 7
    if config_overrides:
        config.update(config_overrides)

    monkeypatch.setattr("src.system.notification_router.get_user_data_dir", lambda: tmp_path)

    fixed_hour = hour

    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 5, 2, fixed_hour, 0, 0)

    monkeypatch.setattr("src.system.notification_router.datetime.datetime", FixedDatetime)
    return NotificationRouter(config)


def test_daily_cap_blocks_after_four_low_priority(tmp_path, monkeypatch):
    """Four low-priority routes (spaced >45 min) are approved; 5th is blocked."""
    monkeypatch.setattr("src.system.notification_router.get_user_data_dir", lambda: tmp_path)

    current_hour = [9]

    class AdvancingDatetime(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 5, 2, current_hour[0], 0, 0)

    monkeypatch.setattr("src.system.notification_router.datetime.datetime", AdvancingDatetime)

    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = True
    config["quiet_hours_start"] = 22
    config["quiet_hours_end"] = 7

    router = NotificationRouter(config)
    approved = []
    router.notification_approved.connect(lambda msg, nt: approved.append(nt))

    # Route 4 unique types, each 1 hour apart so min_interval never triggers
    four_types = ["idle-checkin", "eod-summary", "email-alert", "task-blocked"]
    for i, t in enumerate(four_types):
        current_hour[0] = 9 + i  # 9, 10, 11, 12 — each >45 min apart
        assert router.route(t, "msg", "low"), f"{t} should be approved (attempt {i+1}/4)"

    assert len(approved) == 4

    # 5th attempt at hour 13 — daily cap reached
    current_hour[0] = 13
    assert not router.route("morning-greeting", "Hello", "low")


def test_snooze_blocks_all_notifications(tmp_path, monkeypatch):
    router = _make_router(tmp_path, monkeypatch, hour=10)
    router.snooze(hours=1)

    assert router.is_snoozed() is True
    assert not router.route("morning-greeting", "Hello", "low")
    assert not router.route("idle-checkin", "Hey", "low")


def test_clear_snooze_restores_routing(tmp_path, monkeypatch):
    router = _make_router(tmp_path, monkeypatch, hour=10)
    router.snooze(hours=1)
    router.clear_snooze()

    assert router.is_snoozed() is False
    assert router.route("morning-greeting", "Hello", "low")


def test_disable_category_blocks_that_type(tmp_path, monkeypatch):
    router = _make_router(tmp_path, monkeypatch, hour=10)
    router.disable_category("morning-greeting")

    assert not router.route("morning-greeting", "Hello", "low")
    # Other types still work
    assert router.route("idle-checkin", "Hey", "low")


def test_enable_category_restores_routing(tmp_path, monkeypatch):
    router = _make_router(tmp_path, monkeypatch, hour=10)
    router.disable_category("morning-greeting")
    router.enable_category("morning-greeting")

    assert router.route("morning-greeting", "Hello", "low")


def test_state_persists_across_router_instances(tmp_path, monkeypatch):
    monkeypatch.setattr("src.system.notification_router.get_user_data_dir", lambda: tmp_path)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 5, 2, 10, 0, 0)

    monkeypatch.setattr("src.system.notification_router.datetime.datetime", FixedDatetime)

    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = True
    config["quiet_hours_start"] = 22
    config["quiet_hours_end"] = 7

    router1 = NotificationRouter(config)
    assert router1.route("morning-greeting", "Hello", "low")

    # New router instance loads persisted state
    router2 = NotificationRouter(config)
    # Should be blocked by min_interval (same timestamp)
    assert not router2.route("morning-greeting", "Hello again", "low")


def test_update_last_interaction(tmp_path, monkeypatch):
    router = _make_router(tmp_path, monkeypatch, hour=10)
    assert router.get_last_interaction() == 0
    router.update_last_interaction()
    assert router.get_last_interaction() > 0
