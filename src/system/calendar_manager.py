from __future__ import annotations

import logging
import datetime
import threading
from typing import Optional, List

from src.core.config_manager import get_user_data_dir
from src.core.periodic_thread import PeriodicThread

logger = logging.getLogger(__name__)


class CalendarManager:
    def __init__(self, config: dict, event_bus=None) -> None:
        self._config = config
        self._event_bus = event_bus
        self._thread: Optional[PeriodicThread] = None
        self._events: List[dict] = []
        self._is_polling = False

    def start(self) -> None:
        self._poll()
        self._thread = PeriodicThread(15 * 60 * 1000, self._poll)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self._thread = None

    def get_next_event(self) -> Optional[dict]:
        if not self._events:
            return None
        return self._events[0]

    def _poll(self) -> None:
        provider = self._config.get("calendar_provider", "none")
        if provider == "none":
            self._events = []
            self._update_events(self._events)
            return
        if self._is_polling:
            return
        self._is_polling = True
        threading.Thread(target=self._fetch_google_calendar, daemon=True).start()

    def _fetch_google_calendar(self) -> None:
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
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
                    try:
                        creds = flow.run_local_server(port=0, timeout_seconds=120)
                    except Exception as oauth_err:
                        logger.error("Google OAuth timed out or failed: %s", oauth_err)
                        self._update_events([])
                        return
                    with open(token_path, "w") as token:
                        token.write(creds.to_json())
                else:
                    logger.warning("No credentials.json found for Google Calendar in ~/.kibo")
                    self._update_events([])
                    return

            service = build("calendar", "v3", credentials=creds)
            now = datetime.datetime.utcnow().isoformat() + "Z"
            lookahead_mins = self._config.get("calendar_lookahead_minutes", 60)
            end_time = (
                datetime.datetime.utcnow() + datetime.timedelta(minutes=lookahead_mins)
            ).isoformat() + "Z"
            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    timeMax=end_time,
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])
            parsed_events = [
                {
                    "title": e.get("summary", "Untitled Event"),
                    "start_time": e["start"].get("dateTime", e["start"].get("date")),
                }
                for e in events
            ]
            self._update_events(parsed_events)

        except ImportError:
            logger.warning("Google API client not installed.")
            self._update_events([])
        except Exception as e:
            logger.error("Failed to fetch Google Calendar: %s", e)
            self._update_events([])

    def _update_events(self, events: List[dict]) -> None:
        self._events = events
        if self._event_bus:
            self._event_bus.emit("events_updated", self._events)
        self._is_polling = False
