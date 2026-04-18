import datetime
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from src.ai.brain import SensorData
from src.system.notification_router import NotificationRouter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProactiveContext:
    idle_minutes: int
    current_hour: int
    tasks_pending: int
    tasks_blocked: int
    tasks_done_today: int
    next_meeting_minutes: int
    unread_emails: int
    battery_percent: Optional[float]


@dataclass(frozen=True)
class ProactiveRule:
    type: str
    condition: Callable[[ProactiveContext], bool]
    message: Callable[[ProactiveContext], str]
    priority: str
    enabled_phase: int


RULES = [
    ProactiveRule(
        type="meeting-reminder",
        condition=lambda ctx: 0 < ctx.next_meeting_minutes <= 30,
        message=lambda ctx: f"Meeting in {ctx.next_meeting_minutes} min!",
        priority="high",
        enabled_phase=3,
    ),
    ProactiveRule(
        type="battery-low",
        condition=lambda ctx: ctx.battery_percent is not None and ctx.battery_percent < 20,
        message=lambda _: "Running low on battery...",
        priority="medium",
        enabled_phase=1,
    ),
    ProactiveRule(
        type="task-blocked",
        condition=lambda ctx: ctx.tasks_blocked > 0,
        message=lambda ctx: f"{ctx.tasks_blocked} task(s) are blocked.",
        priority="medium",
        enabled_phase=2,
    ),
    ProactiveRule(
        type="morning-greeting",
        condition=lambda ctx: 7 <= ctx.current_hour < 9,
        message=lambda _: "Good morning! Ready to get things done?",
        priority="low",
        enabled_phase=1,
    ),
    ProactiveRule(
        type="idle-checkin",
        condition=lambda ctx: ctx.idle_minutes > 45 and ctx.tasks_pending > 0,
        message=lambda ctx: (
            f"You've been idle {ctx.idle_minutes} min. {ctx.tasks_pending} task(s) waiting."
        ),
        priority="low",
        enabled_phase=2,
    ),
    ProactiveRule(
        type="eod-summary",
        condition=lambda ctx: 16 <= ctx.current_hour < 19 and ctx.tasks_done_today >= 3,
        message=lambda ctx: f"Great work! {ctx.tasks_done_today} tasks done today.",
        priority="low",
        enabled_phase=2,
    ),
]


class ProactiveEngine(QObject):
    proactive_notification = Signal(str, str, str)

    def __init__(self, config: dict, router: NotificationRouter, task_runner=None) -> None:
        super().__init__()
        self._config = config
        self._router = router
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._battery_percent: Optional[float] = None
        self._next_meeting_minutes = -1
        self._unread_emails = -1
        self._phase = self._compute_phase(config)

        self._tasks_pending = 0
        self._tasks_blocked = 0
        self._tasks_done_today = 0
        self._last_tick_date: Optional[datetime.date] = None
        if task_runner is not None:
            self._sync_task_state(task_runner)

    @staticmethod
    def _compute_phase(config: dict) -> int:
        if not config.get("proactive_enabled", True):
            return 1
        return 3 if config.get("calendar_provider", "none") != "none" else 2

    def _sync_task_state(self, task_runner) -> None:
        """Load task counters from persistent storage on startup."""
        today = datetime.date.today()
        today_start = int(datetime.datetime(today.year, today.month, today.day).timestamp())
        tasks = task_runner.get_tasks()
        self._tasks_pending = sum(1 for t in tasks if t.get("state") == "pending")
        self._tasks_blocked = sum(1 for t in tasks if t.get("state") == "blocked")
        self._tasks_done_today = sum(
            1
            for t in tasks
            if t.get("state") == "completed" and (t.get("completed_at") or 0) >= today_start
        )

    def start(self) -> None:
        self._timer.start(60000)

    def stop(self) -> None:
        self._timer.stop()

    def update_last_interaction(self) -> None:
        self._router.update_last_interaction()

    @Slot(dict)
    def on_config_changed(self, new_config: dict) -> None:
        self._config = new_config
        self._phase = self._compute_phase(new_config)

    @Slot(SensorData)
    def on_sensor_update(self, data: SensorData) -> None:
        self._battery_percent = data.battery_percent

    @Slot(list)
    def on_calendar_updated(self, events: list[dict]) -> None:
        if not events:
            self._next_meeting_minutes = -1
            return

        now = datetime.datetime.now()
        next_event = events[0]
        try:
            start = datetime.datetime.fromisoformat(next_event.get("start_time", ""))
            diff = (start - now).total_seconds() / 60.0
            self._next_meeting_minutes = int(diff) if diff > 0 else -1
        except Exception:
            self._next_meeting_minutes = -1

    @Slot(dict)
    def on_task_completed(self, task: dict) -> None:
        self._tasks_done_today += 1
        self._tasks_pending = max(0, self._tasks_pending - 1)

    @Slot(dict)
    def on_task_blocked(self, task: dict) -> None:
        self._tasks_blocked += 1
        self._tasks_pending = max(0, self._tasks_pending - 1)

    def _on_tick(self) -> None:
        if not self._config.get("proactive_enabled", True):
            return

        today = datetime.date.today()
        if self._last_tick_date is not None and today != self._last_tick_date:
            logger.info("Day rollover detected; resetting daily task counter.")
            self._tasks_done_today = 0
        self._last_tick_date = today

        now = int(datetime.datetime.now().timestamp())
        last_interaction = self._router.get_last_interaction()
        idle_mins = (now - last_interaction) // 60 if last_interaction > 0 else 0

        ctx = ProactiveContext(
            idle_minutes=idle_mins,
            current_hour=datetime.datetime.now().hour,
            tasks_pending=self._tasks_pending,
            tasks_blocked=self._tasks_blocked,
            tasks_done_today=self._tasks_done_today,
            next_meeting_minutes=self._next_meeting_minutes,
            unread_emails=self._unread_emails,
            battery_percent=self._battery_percent,
        )

        for rule in RULES:
            if rule.enabled_phase <= self._phase and rule.condition(ctx):
                self.proactive_notification.emit(rule.type, rule.message(ctx), rule.priority)
                break
