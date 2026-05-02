import dataclasses
import datetime
import json
import logging
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from src.core.config_manager import get_user_data_dir
from src.system.proactive_policy import COOLDOWNS_MINS, ProactivePolicy, RouterState
from src.system.proactive_types import ProactiveEvent

logger = logging.getLogger(__name__)


def _default_state() -> RouterState:
    return RouterState(
        daily_utterance_count=0,
        daily_utterance_date=datetime.date.today(),
        last_utterance_ts=0,
        per_rule_last_fired={},
        snoozed_until=0,
        disabled_categories=frozenset(),
        last_user_interaction=0,
    )


def _state_to_dict(s: RouterState) -> dict:
    return {
        "daily_utterance_count": s.daily_utterance_count,
        "daily_utterance_date": s.daily_utterance_date.isoformat(),
        "last_utterance_ts": s.last_utterance_ts,
        "per_rule_last_fired": s.per_rule_last_fired,
        "snoozed_until": s.snoozed_until,
        "disabled_categories": sorted(s.disabled_categories),
        "last_user_interaction": s.last_user_interaction,
    }


def _state_from_dict(d: dict) -> RouterState:
    try:
        return RouterState(
            daily_utterance_count=int(d.get("daily_utterance_count", 0)),
            daily_utterance_date=date.fromisoformat(
                d.get("daily_utterance_date", datetime.date.today().isoformat())
            ),
            last_utterance_ts=int(d.get("last_utterance_ts", 0)),
            per_rule_last_fired={str(k): int(v) for k, v in d.get("per_rule_last_fired", {}).items()},
            snoozed_until=int(d.get("snoozed_until", 0)),
            disabled_categories=frozenset(d.get("disabled_categories", [])),
            last_user_interaction=int(d.get("last_user_interaction", 0)),
        )
    except Exception:
        return _default_state()


class NotificationRouter(QObject):
    notification_approved = Signal(str, str)  # (message, notification_type)

    def __init__(self, config: dict) -> None:
        super().__init__()
        self._config = config
        self._state_file: Path = get_user_data_dir() / "proactive_state.json"
        self._state: RouterState = self._load_state()
        self._policy = ProactivePolicy()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load_state(self) -> RouterState:
        if self._state_file.exists():
            try:
                raw = json.loads(self._state_file.read_text("utf-8"))
                # Reject legacy format that lacks the new fields.
                if "daily_utterance_count" not in raw:
                    return _default_state()
                return _state_from_dict(raw)
            except Exception:
                pass
        return _default_state()

    def _save_state(self) -> None:
        try:
            self._state_file.write_text(
                json.dumps(_state_to_dict(self._state), indent=2), "utf-8"
            )
        except Exception as e:
            logger.error("Failed to save proactive state: %s", e)

    # ── routing ───────────────────────────────────────────────────────────────

    def route(self, notification_type: str, message: str, priority: str = "low") -> bool:
        now = datetime.datetime.now()
        event = ProactiveEvent(type=notification_type, source_data={"priority": priority})
        decision = self._policy.evaluate(event, self._state, self._config, clock=now)

        if not decision.approved:
            return False

        now_ts = int(now.timestamp())
        new_fired = {**self._state.per_rule_last_fired, notification_type: now_ts}

        if priority == "low":
            current_date = now.date()
            count = (
                self._state.daily_utterance_count
                if self._state.daily_utterance_date == current_date
                else 0
            )
            self._state = dataclasses.replace(
                self._state,
                daily_utterance_count=count + 1,
                daily_utterance_date=current_date,
                last_utterance_ts=now_ts,
                per_rule_last_fired=new_fired,
            )
        else:
            self._state = dataclasses.replace(
                self._state,
                per_rule_last_fired=new_fired,
            )

        self._save_state()
        self.notification_approved.emit(message, notification_type)
        return True

    # ── controls ──────────────────────────────────────────────────────────────

    def snooze(self, hours: int = 1) -> None:
        until = int(
            (datetime.datetime.now() + datetime.timedelta(hours=hours)).timestamp()
        )
        self._state = dataclasses.replace(self._state, snoozed_until=until)
        self._save_state()

    def clear_snooze(self) -> None:
        self._state = dataclasses.replace(self._state, snoozed_until=0)
        self._save_state()

    def is_snoozed(self) -> bool:
        return self._state.snoozed_until > int(datetime.datetime.now().timestamp())

    def disable_category(self, category: str) -> None:
        new_disabled = self._state.disabled_categories | frozenset({category})
        self._state = dataclasses.replace(self._state, disabled_categories=new_disabled)
        self._save_state()

    def enable_category(self, category: str) -> None:
        new_disabled = self._state.disabled_categories - frozenset({category})
        self._state = dataclasses.replace(self._state, disabled_categories=new_disabled)
        self._save_state()

    def disable_proactivity(self) -> None:
        """Convenience: set proactive_enabled=False in live config (does not persist to file)."""
        self._config = {**self._config, "proactive_enabled": False}

    # ── legacy helpers ────────────────────────────────────────────────────────

    def is_quiet_hours(self) -> bool:
        from src.system.proactive_policy import _is_quiet_hours
        return _is_quiet_hours(datetime.datetime.now(), self._config)

    def get_last_interaction(self) -> int:
        return self._state.last_user_interaction

    def update_last_interaction(self) -> None:
        ts = int(datetime.datetime.now().timestamp())
        self._state = dataclasses.replace(self._state, last_user_interaction=ts)
        self._save_state()

    def get_state(self) -> RouterState:
        return self._state

    @Slot(dict)
    def on_config_changed(self, new_config: dict) -> None:
        self._config = new_config
