import logging
import datetime
from typing import Optional, List
from pathlib import Path
import json
import threading

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
        self._is_polling = False
        
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
            
        if self._is_polling:
            return

        self._is_polling = True
        # Run Google calendar fetch in a background thread so OAuth doesn't block the UI
        threading.Thread(target=self._fetch_google_calendar, daemon=True).start()

    def _fetch_google_calendar(self):
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            
            SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
            token_path = get_user_data_dir() / "google_token.json"
            creds_path = get_user_data_dir() / "credentials.json"
            
            creds = None
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
                
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                elif creds_path.exists():
                    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                    creds = flow.run_local_server(port=0)
                    with open(token_path, 'w') as token:
                        token.write(creds.to_json())
                else:
                    logger.warning("No credentials.json found for Google Calendar in ~/.kibo")
                    self._update_events([])
                    return

            service = build('calendar', 'v3', credentials=creds)
            
            now = datetime.datetime.utcnow().isoformat() + 'Z'
            lookahead_mins = self._config.get("calendar_lookahead_minutes", 60)
            end_time = (datetime.datetime.utcnow() + datetime.timedelta(minutes=lookahead_mins)).isoformat() + 'Z'
            
            events_result = service.events().list(calendarId='primary', timeMin=now,
                                                  timeMax=end_time, maxResults=10, singleEvents=True,
                                                  orderBy='startTime').execute()
            events = events_result.get('items', [])
            
            parsed_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                parsed_events.append({
                    "title": event.get('summary', 'Untitled Event'),
                    "start_time": start
                })
            
            self._update_events(parsed_events)
            
        except ImportError:
            logger.warning("Google API client not installed. Run: pip install google-auth-oauthlib google-api-python-client")
            self._update_events([])
        except Exception as e:
            logger.error(f"Failed to fetch Google Calendar: {e}")
            self._update_events([])
            
    def _update_events(self, events):
        self._events = events
        # Note: PySide6 handles cross-thread signal emission seamlessly using QueuedConnection
        self.events_updated.emit(self._events)
        self._is_polling = False
