import logging
import datetime
from typing import Optional, List, Dict
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer

from config_manager import get_user_data_dir

logger = logging.getLogger(__name__)

class CalendarManager(QObject):
    events_updated = Signal(list)   # list of CalendarEvent dicts

    def __init__(self, config: dict) -> None:
        super().__init__()
        self._config = config
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._events: List[dict] = []
        
    def start(self) -> None:
        # Initial poll immediately, then every 15 minutes
        self._poll()
        self._timer.start(15 * 60 * 1000)

    def stop(self) -> None:
        self._timer.stop()

    def get_next_event(self) -> Optional[dict]:
        if not self._events:
            return None
        return self._events[0]

    def _poll(self) -> None:
        provider = self._config.get("calendar_provider", "none")
        if provider == "none":
            self._events = []
            self.events_updated.emit(self._events)
            return

        # Placeholder for actual Google/Outlook/CalDAV integration.
        # Since the spec says "Google provider first", but we don't have
        # credentials setup in the CLI automatically, we will mock it or leave
        # it as a stub that reads a local file for testing, or just log.
        logger.info(f"Calendar poll for provider: {provider}")
        
        # Real integration would go here using google-auth-oauthlib
        # For the prototype/v4 milestone, we will try to read a mock file
        # so it can be tested easily.
        mock_file = get_user_data_dir() / "mock_calendar.json"
        events = []
        if mock_file.exists():
            try:
                import json
                events = json.loads(mock_file.read_text("utf-8"))
            except Exception:
                pass
                
        # Filter past events and sort
        now = datetime.datetime.now().isoformat()
        future_events = [e for e in events if e.get("start_time", "") > now]
        future_events.sort(key=lambda x: x.get("start_time", ""))
        
        self._events = future_events
        self.events_updated.emit(self._events)
