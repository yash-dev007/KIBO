import datetime
import pytest
from unittest.mock import MagicMock
from src.api.event_bus import EventBus
from src.system.proactive_engine import ProactiveEngine, ProactiveContext, RULES
from src.system.notification_router import NotificationRouter
from src.core.config_manager import DEFAULT_CONFIG


@pytest.fixture
def bus():
    return EventBus()


def _make_router(tmp_path, monkeypatch):
    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = True
    monkeypatch.setattr("src.system.notification_router.get_user_data_dir", lambda: tmp_path)
    return NotificationRouter(config)


def _fixed_clock(hour=10, minute=0):
    dt = datetime.datetime(2026, 5, 8, hour, minute)
    return lambda: dt


def test_tick_emits_morning_greeting(tmp_path, monkeypatch, bus):
    router = _make_router(tmp_path, monkeypatch)
    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = True

    clock = _fixed_clock(hour=9)
    engine = ProactiveEngine(config, router=router, clock_fn=clock, event_bus=bus)
    engine._start_time = clock() - datetime.timedelta(minutes=5)

    received = []
    bus.on("proactive_notification", lambda t, m, p: received.append((t, m, p)))
    engine._on_tick()

    assert any(r[0] == "morning-greeting" for r in received)


def test_tick_skipped_when_disabled(tmp_path, monkeypatch, bus):
    router = _make_router(tmp_path, monkeypatch)
    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = False

    engine = ProactiveEngine(config, router=router, event_bus=bus)
    received = []
    bus.on("proactive_notification", lambda t, m, p: received.append(t))
    engine._on_tick()

    assert received == []


def test_on_task_completed_updates_counters(tmp_path, monkeypatch, bus):
    router = _make_router(tmp_path, monkeypatch)
    config = dict(DEFAULT_CONFIG)
    engine = ProactiveEngine(config, router=router, event_bus=bus)
    engine._tasks_pending = 2

    engine.on_task_completed({"id": "x"})
    assert engine._tasks_done_today == 1
    assert engine._tasks_pending == 1


def test_on_task_blocked_updates_counters(tmp_path, monkeypatch, bus):
    router = _make_router(tmp_path, monkeypatch)
    config = dict(DEFAULT_CONFIG)
    engine = ProactiveEngine(config, router=router, event_bus=bus)
    engine._tasks_pending = 1

    engine.on_task_blocked({"id": "x"})
    assert engine._tasks_blocked == 1
    assert engine._tasks_pending == 0


def test_battery_low_rule_fires(tmp_path, monkeypatch, bus):
    router = _make_router(tmp_path, monkeypatch)
    config = dict(DEFAULT_CONFIG)
    config["proactive_enabled"] = True

    clock = _fixed_clock(hour=14)
    engine = ProactiveEngine(config, router=router, clock_fn=clock, event_bus=bus)
    engine._battery_percent = 15.0

    received = []
    bus.on("proactive_notification", lambda t, m, p: received.append(t))
    engine._on_tick()

    assert "battery-low" in received
