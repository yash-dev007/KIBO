import pytest
from calendar_manager import CalendarManager
from config_manager import DEFAULT_CONFIG
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

def test_calendar_manager_mock(tmp_path, monkeypatch):
    config = dict(DEFAULT_CONFIG)
    config["calendar_provider"] = "google"
    
    monkeypatch.setattr("calendar_manager.get_user_data_dir", lambda: tmp_path)
    
    now = datetime.datetime.now()
    future_time = (now + datetime.timedelta(minutes=30)).isoformat()
    past_time = (now - datetime.timedelta(minutes=30)).isoformat()
    
    mock_events = [
        {"start_time": past_time, "title": "Old Meeting"},
        {"start_time": future_time, "title": "Upcoming Meeting"}
    ]
    
    import json
    (tmp_path / "mock_calendar.json").write_text(json.dumps(mock_events), "utf-8")
    
    mgr = CalendarManager(config)
    mgr._poll()
    
    next_event = mgr.get_next_event()
    assert next_event is not None
    assert next_event["title"] == "Upcoming Meeting"
