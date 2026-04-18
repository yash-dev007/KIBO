import pytest
from src.system.calendar_manager import CalendarManager
from src.core.config_manager import DEFAULT_CONFIG
import datetime

def test_calendar_manager_none(tmp_path, monkeypatch):
    config = dict(DEFAULT_CONFIG)
    config["calendar_provider"] = "none"
    
    mgr = CalendarManager(config)
    events = []
    mgr.events_updated.connect(events.extend)
    
    mgr._poll()
    
    assert len(events) == 0
    assert mgr.get_next_event() is None

def test_calendar_manager_update_events(tmp_path, monkeypatch):
    """Test _update_events directly — bypasses OAuth flow entirely."""
    config = dict(DEFAULT_CONFIG)
    config["calendar_provider"] = "google"

    monkeypatch.setattr("src.system.calendar_manager.get_user_data_dir", lambda: tmp_path)

    now = datetime.datetime.now()
    future_time = (now + datetime.timedelta(minutes=30)).isoformat()
    past_time = (now - datetime.timedelta(minutes=30)).isoformat()

    mgr = CalendarManager(config)

    received = []
    mgr.events_updated.connect(received.extend)

    # Simulate what _fetch_google_calendar would produce after parsing
    parsed_events = [
        {"title": "Old Meeting", "start_time": past_time},
        {"title": "Upcoming Meeting", "start_time": future_time},
    ]
    mgr._update_events(parsed_events)

    assert mgr.get_next_event() is not None
    assert mgr.get_next_event()["title"] == "Old Meeting"  # first in list as returned
    assert len(received) == 2  # both events passed to the signal
