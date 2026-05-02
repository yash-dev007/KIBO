import datetime
from dataclasses import dataclass
from datetime import date
from typing import Any

from src.system.proactive_types import ProactiveDecision, ProactiveEvent

DAILY_CAP: int = 4
MIN_INTERVAL_SECS: int = 45 * 60

# Minutes of cooldown per rule type; 0 means no cooldown enforcement.
COOLDOWNS_MINS: dict[str, int] = {
    "morning-greeting": 720,   # effectively once per day
    "idle-checkin": 60,
    "eod-summary": 480,
    "cpu-panic": 5,
    "battery-low": 30,
    "meeting-reminder": 25,
    "email-alert": 120,
    "task-blocked": 60,
    "reminder": 0,
}


@dataclass(frozen=True)
class RouterState:
    daily_utterance_count: int
    daily_utterance_date: date
    last_utterance_ts: int               # unix ts of last approved low-priority utterance
    per_rule_last_fired: dict[str, int]  # rule_type → unix ts
    snoozed_until: int                   # unix ts; 0 = not snoozed
    disabled_categories: frozenset[str]
    last_user_interaction: int           # unix ts


class ProactivePolicy:
    """Stateless evaluator. Returns a ProactiveDecision for a given event, state, config, and clock."""

    def evaluate(
        self,
        event: ProactiveEvent,
        state: RouterState,
        config: dict[str, Any],
        clock: datetime.datetime,
    ) -> ProactiveDecision:
        priority = event.source_data.get("priority", "low")
        bypass_cap: bool = bool(event.source_data.get("bypass_cap", False))

        if not config.get("proactive_enabled", True):
            return ProactiveDecision(approved=False, reason="proactive_disabled", event=event)

        if priority != "high" and not bypass_cap:
            if _is_quiet_hours(clock, config):
                return ProactiveDecision(approved=False, reason="quiet_hours", event=event)

        now_ts = int(clock.timestamp())

        if state.snoozed_until > now_ts:
            return ProactiveDecision(approved=False, reason="snoozed", event=event)

        if event.type in state.disabled_categories:
            return ProactiveDecision(approved=False, reason="category_disabled", event=event)

        notification_types: dict = config.get("notification_types", {})
        if not notification_types.get(event.type, True):
            return ProactiveDecision(approved=False, reason="category_disabled", event=event)

        if priority == "low" and not bypass_cap:
            current_date = clock.date()
            count = state.daily_utterance_count if state.daily_utterance_date == current_date else 0
            if count >= DAILY_CAP:
                return ProactiveDecision(approved=False, reason="daily_cap", event=event)

            if state.last_utterance_ts > 0 and now_ts - state.last_utterance_ts < MIN_INTERVAL_SECS:
                return ProactiveDecision(approved=False, reason="min_interval", event=event)

        if event.type == "morning-greeting" and clock.hour < 8:
            return ProactiveDecision(approved=False, reason="too_early", event=event)

        cooldown_mins = COOLDOWNS_MINS.get(event.type, 60)
        if cooldown_mins > 0:
            last_fired = state.per_rule_last_fired.get(event.type, 0)
            if last_fired > 0 and now_ts - last_fired < cooldown_mins * 60:
                return ProactiveDecision(approved=False, reason="cooldown", event=event)

        return ProactiveDecision(approved=True, reason="approved", event=event)


def _is_quiet_hours(clock: datetime.datetime, config: dict[str, Any]) -> bool:
    start: int = config.get("quiet_hours_start", 22)
    end: int = config.get("quiet_hours_end", 7)
    hour = clock.hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end
