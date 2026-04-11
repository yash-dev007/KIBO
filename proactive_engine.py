import logging
import datetime
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal, QTimer, Slot

from brain import SensorData
from notification_router import NotificationRouter

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
    # HIGH — bypass quiet hours
    ProactiveRule(
        type="meeting-reminder",
        condition=lambda ctx: 0 < ctx.next_meeting_minutes <= 30,
        message=lambda ctx: f"⏰ Meeting in {ctx.next_meeting_minutes} min!",
        priority="high",
        enabled_phase=3,
    ),
    # MEDIUM
    ProactiveRule(
        type="battery-low",
        condition=lambda ctx: ctx.battery_percent is not None and ctx.battery_percent < 20,
        message=lambda _: "🔋 Running low on battery...",
        priority="medium",
        enabled_phase=1,
    ),
    ProactiveRule(
        type="task-blocked",
        condition=lambda ctx: ctx.tasks_blocked > 0,
        message=lambda ctx: f"⚠️ {ctx.tasks_blocked} task(s) are blocked.",
        priority="medium",
        enabled_phase=3,
    ),
    # LOW
    ProactiveRule(
        type="morning-greeting",
        condition=lambda ctx: 7 <= ctx.current_hour < 9,
        message=lambda ctx: "☀️ Good morning! Ready to get things done?",
        priority="low",
        enabled_phase=1,
    ),
    ProactiveRule(
        type="idle-checkin",
        condition=lambda ctx: ctx.idle_minutes > 45 and ctx.tasks_pending > 0,
        message=lambda ctx: f"💤 You've been idle {ctx.idle_minutes} min. {ctx.tasks_pending} task(s) waiting.",
        priority="low",
        enabled_phase=3,
    ),
    ProactiveRule(
        type="eod-summary",
        condition=lambda ctx: 16 <= ctx.current_hour < 19 and ctx.tasks_done_today >= 3,
        message=lambda ctx: f"✅ Great work! {ctx.tasks_done_today} tasks done today.",
        priority="low",
        enabled_phase=3,
    ),
    ProactiveRule(
        type="idle-checkin",
        condition=lambda ctx: ctx.idle_minutes > 60,
        message=lambda _: "👋 Still there? Anything I can help with?",
        priority="low",
        enabled_phase=1,
    ),
]

class ProactiveEngine(QObject):
    proactive_notification = Signal(str, str, str)  # (notification_type, message, priority)

    def __init__(self, config: dict, router: NotificationRouter) -> None:
        super().__init__()
        self._config = config
        self._router = router
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._battery_percent: Optional[float] = None
        
        # Phase 3 placeholders
        self._tasks_pending = 0
        self._tasks_blocked = 0
        self._tasks_done_today = 0
        self._next_meeting_minutes = -1
        self._unread_emails = -1

    def start(self) -> None:
        self._timer.start(60000)  # 60s tick
        
    def stop(self) -> None:
        self._timer.stop()

    def update_last_interaction(self) -> None:
        self._router.update_last_interaction()

    @Slot(SensorData)
    def on_sensor_update(self, data: SensorData) -> None:
        self._battery_percent = data.battery_percent

    def _on_tick(self) -> None:
        if not self._config.get("proactive_enabled", True):
            return

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
            battery_percent=self._battery_percent
        )

        for rule in RULES:
            # We only evaluate Phase 1 and 2 rules for now
            if rule.enabled_phase <= 2 and rule.condition(ctx):
                self.proactive_notification.emit(rule.type, rule.message(ctx), rule.priority)
                # Route evaluates cooldowns internally. We emit, and the router decides whether to approve.
                # But wait, if router blocks it, should we try the next rule?
                # The spec says "priority-ordered, first match wins", so we break regardless.
                break
