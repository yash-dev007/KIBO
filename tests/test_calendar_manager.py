import pytest
import datetime
from src.api.event_bus import EventBus
from src.system.calendar_manager import CalendarManager
from src.core.config_manager import DEFAULT_CONFIG


@pytest.fixture
def bus():
    return EventBus()


def test_calendar_manager_none(bus):
    config = dict(DEFAULT_CONFIG)
    config["calendar_provider"] = "none"

    mgr = CalendarManager(config, event_bus=bus)
    events = []
    bus.on("events_updated", events.extend)

    mgr._poll()

    assert len(events) == 0
    assert mgr.get_next_event() is None


def test_calendar_manager_update_events(tmp_path, monkeypatch, bus):
    config = dict(DEFAULT_CONFIG)
    config["calendar_provider"] = "google"
    monkeypatch.setattr("src.system.calendar_manager.get_user_data_dir", lambda: tmp_path)

    now = datetime.datetime.now()
    future_time = (now + datetime.timedelta(minutes=30)).isoformat()
    past_time = (now - datetime.timedelta(minutes=30)).isoformat()

    mgr = CalendarManager(config, event_bus=bus)

    received = []
    bus.on("events_updated", received.extend)

    parsed_events = [
        {"title": "Old Meeting", "start_time": past_time},
        {"title": "Upcoming Meeting", "start_time": future_time},
    ]
    mgr._update_events(parsed_events)

    assert mgr.get_next_event() is not None
    assert mgr.get_next_event()["title"] == "Old Meeting"
    assert len(received) == 2


def test_events_updated_event_emitted(bus):
    config = dict(DEFAULT_CONFIG)
    config["calendar_provider"] = "none"

    mgr = CalendarManager(config, event_bus=bus)
    emitted = []
    bus.on("events_updated", lambda evts: emitted.append(evts))

    mgr._poll()
    assert len(emitted) == 1
    assert emitted[0] == []
