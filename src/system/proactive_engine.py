from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from src.ai.brain import SensorData
from src.system.notification_router import NotificationRouter
from src.core.periodic_thread import PeriodicThread

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
    cpu_percent: Optional[float]
    app_open_minutes: int


@dataclass(frozen=True)
class ProactiveRule:
    type: str
    condition: Callable[[ProactiveContext], bool]
    message: Callable[[ProactiveContext], str]
    priority: str


RULES: list[ProactiveRule] = [
    ProactiveRule(
        type="morning-greeting",
        condition=lambda ctx: 8 <= ctx.current_hour < 12 and ctx.app_open_minutes >= 2,
        message=lambda _: "Good morning! Ready to get things done?",
        priority="low",
    ),
    ProactiveRule(
        type="idle-checkin",
        condition=lambda ctx: ctx.idle_minutes >= 60,
        message=lambda ctx: f"You've been away for {ctx.idle_minutes} minutes. Still there?",
        priority="low",
    ),
    ProactiveRule(
        type="eod-summary",
        condition=lambda ctx: 17 <= ctx.current_hour < 20 and ctx.tasks_done_today >= 1,
        message=lambda ctx: f"Nice work today — {ctx.tasks_done_today} task(s) done!",
        priority="low",
    ),
    ProactiveRule(
        type="battery-low",
        condition=lambda ctx: ctx.battery_percent is not None and ctx.battery_percent < 20,
        message=lambda ctx: f"Battery at {ctx.battery_percent:.0f}% — might want to plug in.",
        priority="medium",
    ),
    ProactiveRule(
        type="cpu-panic",
        condition=lambda ctx: ctx.cpu_percent is not None and ctx.cpu_percent > 90,
        message=lambda _: "CPU is spiking — something's working hard.",
        priority="medium",
    ),
    ProactiveRule(
        type="meeting-reminder",
        condition=lambda ctx: 0 < ctx.next_meeting_minutes <= 30,
        message=lambda ctx: f"Meeting in {ctx.next_meeting_minutes} min!",
        priority="medium",
    ),
]


class ProactiveEngine:
    def __init__(
        self,
        config: dict,
        router: NotificationRouter,
        task_runner=None,
        clock_fn: Optional[Callable[[], datetime.datetime]] = None,
        event_bus=None,
    ) -> None:
        self._config = config
        self._router = router
        self._event_bus = event_bus
        self._clock_fn: Callable[[], datetime.datetime] = clock_fn or datetime.datetime.now
        self._thread: Optional[PeriodicThread] = None

        self._battery_percent: Optional[float] = None
        self._cpu_percent: Optional[float] = None
        self._next_meeting_minutes = -1
        self._unread_emails = -1
        self._start_time: datetime.datetime = self._clock_fn()

        self._tasks_pending = 0
        self._tasks_blocked = 0
        self._tasks_done_today = 0
        self._last_tick_date: Optional[datetime.date] = None

        if task_runner is not None:
            self._sync_task_state(task_runner)

    def _sync_task_state(self, task_runner) -> None:
        today = datetime.date.today()
        today_start = int(datetime.datetime(today.year, today.month, today.day).timestamp())
        tasks = task_runner.get_tasks()
        self._tasks_pending = sum(1 for t in tasks if t.get("state") == "pending")
        self._tasks_blocked = sum(1 for t in tasks if t.get("state") == "blocked")
        self._tasks_done_today = sum(
            1 for t in tasks
            if t.get("state") == "completed" and (t.get("completed_at") or 0) >= today_start
        )

    def start(self) -> None:
        # Reset the idle clock so stale timestamps from previous sessions
        # don't trigger "you've been away for N days" on first launch.
        self._router.update_last_interaction()
        self._thread = PeriodicThread(60_000, self._on_tick)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self._thread = None

    def update_last_interaction(self) -> None:
        self._router.update_last_interaction()

    def on_config_changed(self, new_config: dict) -> None:
        self._config = new_config

    def on_sensor_update(self, data: SensorData) -> None:
        self._battery_percent = data.battery_percent
        self._cpu_percent = getattr(data, "cpu_percent", None)

    def on_calendar_updated(self, events: list) -> None:
        if not events:
            self._next_meeting_minutes = -1
            return
        now = self._clock_fn()
        try:
            start = datetime.datetime.fromisoformat(events[0].get("start_time", ""))
            diff = (start - now).total_seconds() / 60.0
            self._next_meeting_minutes = int(diff) if diff > 0 else -1
        except Exception:
            self._next_meeting_minutes = -1

    def on_task_completed(self, task: dict) -> None:
        self._tasks_done_today += 1
        self._tasks_pending = max(0, self._tasks_pending - 1)

    def on_task_blocked(self, task: dict) -> None:
        self._tasks_blocked += 1
        self._tasks_pending = max(0, self._tasks_pending - 1)

    def _on_tick(self) -> None:
        if not self._config.get("proactive_enabled", True):
            return

        now = self._clock_fn()
        today = now.date()
        if self._last_tick_date is not None and today != self._last_tick_date:
            logger.info("Day rollover detected; resetting daily task counter.")
            self._tasks_done_today = 0
        self._last_tick_date = today

        last_interaction = self._router.get_last_interaction()
        now_ts = int(now.timestamp())
        idle_mins = (now_ts - last_interaction) // 60 if last_interaction > 0 else 0
        app_open_mins = int((now - self._start_time).total_seconds() / 60)

        ctx = ProactiveContext(
            idle_minutes=idle_mins,
            current_hour=now.hour,
            tasks_pending=self._tasks_pending,
            tasks_blocked=self._tasks_blocked,
            tasks_done_today=self._tasks_done_today,
            next_meeting_minutes=self._next_meeting_minutes,
            unread_emails=self._unread_emails,
            battery_percent=self._battery_percent,
            cpu_percent=self._cpu_percent,
            app_open_minutes=app_open_mins,
        )

        for rule in RULES:
            if rule.condition(ctx):
                msg = rule.message(ctx)
                allowed = self._router.route(rule.type, msg, rule.priority)
                if allowed and self._event_bus:
                    self._event_bus.emit(
                        "proactive_notification", rule.type, msg, rule.priority
                    )
                break
