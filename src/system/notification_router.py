from __future__ import annotations

import json
import logging
import datetime
from typing import TYPE_CHECKING

from src.core.config_manager import get_user_data_dir

if TYPE_CHECKING:
    from src.api.event_bus import EventBus

logger = logging.getLogger(__name__)


class NotificationRouter:
    def __init__(self, config: dict, event_bus: "EventBus | None" = None) -> None:
        self._event_bus = event_bus
        self._config = config
        self._state_file = get_user_data_dir() / "proactive_state.json"
        self._state = self._load_state()

        self._default_cooldowns = {
            "morning-greeting": 720,
            "idle-checkin": 60,
            "eod-summary": 480,
            "cpu-panic": 5,
            "battery-low": 30,
            "meeting-reminder": 25,
            "email-alert": 120,
            "task-blocked": 60,
        }

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text("utf-8"))
            except Exception:
                pass
        return {"cooldowns": {}, "last_user_interaction": 0}

    def _save_state(self) -> None:
        try:
            self._state_file.write_text(json.dumps(self._state, indent=2), "utf-8")
        except Exception as e:
            logger.error("Failed to save proactive state: %s", e)

    def is_quiet_hours(self) -> bool:
        start = self._config.get("quiet_hours_start", 22)
        end = self._config.get("quiet_hours_end", 7)
        current_hour = datetime.datetime.now().hour

        if start <= end:
            return start <= current_hour < end
        else:
            return current_hour >= start or current_hour < end

    def route(self, notification_type: str, message: str, priority: str = "low") -> bool:
        if not self._config.get("proactive_enabled", True):
            return False

        notification_types = self._config.get("notification_types", {})
        if not notification_types.get(notification_type, True):
            return False

        if priority != "high" and self.is_quiet_hours():
            return False

        now = int(datetime.datetime.now().timestamp())
        cooldowns = self._state.get("cooldowns", {})
        last_sent = cooldowns.get(notification_type, 0)
        cooldown_mins = self._default_cooldowns.get(notification_type, 60)

        if now - last_sent < cooldown_mins * 60:
            return False

        cooldowns[notification_type] = now
        self._state["cooldowns"] = cooldowns
        self._save_state()

        if self._event_bus:
            self._event_bus.emit("notification_approved", message, notification_type)
        return True

    def get_last_interaction(self) -> int:
        return self._state.get("last_user_interaction", 0)

    def update_last_interaction(self) -> None:
        self._state["last_user_interaction"] = int(datetime.datetime.now().timestamp())
        self._save_state()

    def on_config_changed(self, new_config: dict) -> None:
        self._config = new_config
