import dataclasses
import pytest
from datetime import datetime, date, timedelta

from src.system.proactive_types import ProactiveEvent, ProactiveDecision, ProactiveUtterance
from src.system.proactive_policy import ProactivePolicy, RouterState, DAILY_CAP, MIN_INTERVAL_SECS


# ── Helpers ──────────────────────────────────────────────────────────────────

def clock_at(hour: int, minute: int = 0, day: int = 2) -> datetime:
    return datetime(2026, 5, day, hour, minute, 0)


def make_state(**overrides) -> RouterState:
    defaults = dict(
        daily_utterance_count=0,
        daily_utterance_date=date(2026, 5, 2),
        last_utterance_ts=0,
        per_rule_last_fired={},
        snoozed_until=0,
        disabled_categories=frozenset(),
        last_user_interaction=0,
    )
    defaults.update(overrides)
    return RouterState(**defaults)


def make_config(**overrides) -> dict:
    base = {
        "proactive_enabled": True,
        "quiet_hours_start": 22,
        "quiet_hours_end": 7,
    }
    base.update(overrides)
    return base


def evt(type_: str, priority: str = "low", **extra) -> ProactiveEvent:
    return ProactiveEvent(type=type_, source_data={"priority": priority, **extra})


# ── ProactiveEvent ────────────────────────────────────────────────────────────

class TestProactiveEvent:
    def test_fields_accessible(self):
        e = ProactiveEvent(type="battery", source_data={"percent": 15.0})
        assert e.type == "battery"
        assert e.source_data["percent"] == 15.0

    def test_is_immutable(self):
        e = ProactiveEvent(type="morning", source_data={})
        with pytest.raises((AttributeError, TypeError)):
            e.type = "changed"  # type: ignore[misc]

    def test_different_instances_equal_when_same(self):
        a = ProactiveEvent(type="x", source_data={"k": 1})
        b = ProactiveEvent(type="x", source_data={"k": 1})
        assert a == b


# ── ProactiveDecision ─────────────────────────────────────────────────────────

class TestProactiveDecision:
    def test_approved_decision(self):
        e = evt("morning")
        d = ProactiveDecision(approved=True, reason="approved", event=e)
        assert d.approved is True
        assert d.reason == "approved"

    def test_blocked_decision(self):
        e = evt("morning")
        d = ProactiveDecision(approved=False, reason="quiet_hours", event=e)
        assert d.approved is False
        assert d.event is e

    def test_is_immutable(self):
        e = evt("x")
        d = ProactiveDecision(approved=True, reason="ok", event=e)
        with pytest.raises((AttributeError, TypeError)):
            d.approved = False  # type: ignore[misc]


# ── ProactiveUtterance ────────────────────────────────────────────────────────

class TestProactiveUtterance:
    def test_all_fields(self):
        expiry = clock_at(9, 30)
        u = ProactiveUtterance(
            text="Good morning!",
            category="morning-greeting",
            priority="low",
            expiry=expiry,
            delivery_mode="bubble",
            bypass_cap=False,
        )
        assert u.text == "Good morning!"
        assert u.category == "morning-greeting"
        assert u.bypass_cap is False
        assert u.expiry == expiry

    def test_bypass_cap_field(self):
        u = ProactiveUtterance(
            text="Reminder!",
            category="reminder",
            priority="high",
            expiry=clock_at(10),
            delivery_mode="tts+bubble",
            bypass_cap=True,
        )
        assert u.bypass_cap is True


# ── RouterState ───────────────────────────────────────────────────────────────

class TestRouterState:
    def test_defaults_from_helper(self):
        s = make_state()
        assert s.daily_utterance_count == 0
        assert s.snoozed_until == 0
        assert s.disabled_categories == frozenset()

    def test_replace_creates_new_instance(self):
        s = make_state(daily_utterance_count=1)
        s2 = dataclasses.replace(s, daily_utterance_count=2)
        assert s.daily_utterance_count == 1
        assert s2.daily_utterance_count == 2

    def test_is_immutable(self):
        s = make_state()
        with pytest.raises((AttributeError, TypeError)):
            s.daily_utterance_count = 99  # type: ignore[misc]


# ── ProactivePolicy ───────────────────────────────────────────────────────────

class TestProactivePolicy:
    def setup_method(self):
        self.policy = ProactivePolicy()

    # proactive disabled

    def test_blocks_when_proactive_disabled(self):
        d = self.policy.evaluate(
            evt("morning"), make_state(), make_config(proactive_enabled=False), clock_at(9)
        )
        assert not d.approved
        assert d.reason == "proactive_disabled"

    # quiet hours

    def test_blocks_low_priority_during_quiet_hours(self):
        d = self.policy.evaluate(
            evt("morning", priority="low"), make_state(), make_config(), clock_at(23)
        )
        assert not d.approved
        assert d.reason == "quiet_hours"

    def test_blocks_medium_priority_during_quiet_hours(self):
        d = self.policy.evaluate(
            evt("battery-low", priority="medium"), make_state(), make_config(), clock_at(23)
        )
        assert not d.approved
        assert d.reason == "quiet_hours"

    def test_allows_high_priority_during_quiet_hours(self):
        d = self.policy.evaluate(
            evt("meeting-reminder", priority="high"), make_state(), make_config(), clock_at(23)
        )
        assert d.approved

    def test_quiet_hours_wraparound_3am_blocked(self):
        # 22:00 → 07:00 window, 03:00 is inside
        d = self.policy.evaluate(
            evt("morning", priority="low"), make_state(), make_config(), clock_at(3)
        )
        assert d.reason == "quiet_hours"

    def test_quiet_hours_wraparound_8am_allowed(self):
        d = self.policy.evaluate(
            evt("morning", priority="low"), make_state(), make_config(), clock_at(8)
        )
        assert d.reason != "quiet_hours"

    def test_midday_not_quiet_hours(self):
        d = self.policy.evaluate(
            evt("idle-checkin", priority="low"), make_state(), make_config(), clock_at(14)
        )
        assert d.reason != "quiet_hours"

    # snooze

    def test_blocks_when_snoozed(self):
        now = clock_at(10)
        snoozed_until = int((now + timedelta(hours=1)).timestamp())
        d = self.policy.evaluate(
            evt("morning"), make_state(snoozed_until=snoozed_until), make_config(), now
        )
        assert not d.approved
        assert d.reason == "snoozed"

    def test_snooze_expired_does_not_block(self):
        now = clock_at(10)
        expired = int((now - timedelta(minutes=1)).timestamp())
        d = self.policy.evaluate(
            evt("morning"), make_state(snoozed_until=expired), make_config(), now
        )
        assert d.reason != "snoozed"

    def test_snooze_zero_does_not_block(self):
        d = self.policy.evaluate(
            evt("morning"), make_state(snoozed_until=0), make_config(), clock_at(9)
        )
        assert d.reason != "snoozed"

    # disabled category

    def test_blocks_disabled_category(self):
        state = make_state(disabled_categories=frozenset({"morning-greeting"}))
        d = self.policy.evaluate(evt("morning-greeting"), state, make_config(), clock_at(9))
        assert not d.approved
        assert d.reason == "category_disabled"

    def test_non_disabled_category_not_blocked(self):
        state = make_state(disabled_categories=frozenset({"idle-checkin"}))
        d = self.policy.evaluate(evt("morning-greeting"), state, make_config(), clock_at(9))
        assert d.reason != "category_disabled"

    # daily cap (low priority only)

    def test_blocks_low_priority_when_daily_cap_reached(self):
        state = make_state(daily_utterance_count=DAILY_CAP, daily_utterance_date=date(2026, 5, 2))
        d = self.policy.evaluate(evt("idle-checkin", priority="low"), state, make_config(), clock_at(14))
        assert not d.approved
        assert d.reason == "daily_cap"

    def test_medium_priority_bypasses_daily_cap(self):
        state = make_state(daily_utterance_count=DAILY_CAP, daily_utterance_date=date(2026, 5, 2))
        d = self.policy.evaluate(evt("battery-low", priority="medium"), state, make_config(), clock_at(14))
        assert d.reason != "daily_cap"

    def test_high_priority_bypasses_daily_cap(self):
        state = make_state(daily_utterance_count=DAILY_CAP, daily_utterance_date=date(2026, 5, 2))
        d = self.policy.evaluate(evt("meeting-reminder", priority="high"), state, make_config(), clock_at(14))
        assert d.reason != "daily_cap"

    def test_explicit_reminder_bypass_cap_flag(self):
        state = make_state(daily_utterance_count=DAILY_CAP, daily_utterance_date=date(2026, 5, 2))
        d = self.policy.evaluate(
            evt("reminder", priority="low", bypass_cap=True), state, make_config(), clock_at(14)
        )
        assert d.reason != "daily_cap"

    def test_daily_cap_resets_on_new_day(self):
        # Yesterday's state with cap reached
        state = make_state(daily_utterance_count=DAILY_CAP, daily_utterance_date=date(2026, 5, 1))
        # Today's clock
        d = self.policy.evaluate(evt("morning-greeting", priority="low"), state, make_config(), clock_at(9))
        assert d.reason != "daily_cap"

    # min interval (low priority only)

    def test_blocks_low_priority_below_min_interval(self):
        now = clock_at(10)
        recent_ts = int((now - timedelta(minutes=30)).timestamp())
        state = make_state(last_utterance_ts=recent_ts)
        d = self.policy.evaluate(evt("idle-checkin", priority="low"), state, make_config(), now)
        assert not d.approved
        assert d.reason == "min_interval"

    def test_allows_low_priority_after_min_interval(self):
        now = clock_at(10)
        old_ts = int((now - timedelta(minutes=50)).timestamp())
        state = make_state(last_utterance_ts=old_ts)
        d = self.policy.evaluate(evt("idle-checkin", priority="low"), state, make_config(), now)
        assert d.reason != "min_interval"

    def test_medium_priority_bypasses_min_interval(self):
        now = clock_at(10)
        recent_ts = int((now - timedelta(minutes=5)).timestamp())
        state = make_state(last_utterance_ts=recent_ts)
        d = self.policy.evaluate(evt("battery-low", priority="medium"), state, make_config(), now)
        assert d.reason != "min_interval"

    def test_zero_last_utterance_ts_skips_min_interval(self):
        d = self.policy.evaluate(
            evt("morning-greeting", priority="low"), make_state(last_utterance_ts=0), make_config(), clock_at(9)
        )
        assert d.reason != "min_interval"

    # morning-greeting time gate

    def test_morning_greeting_blocked_before_0800(self):
        d = self.policy.evaluate(evt("morning-greeting"), make_state(), make_config(), clock_at(7, 59))
        assert not d.approved
        assert d.reason == "too_early"

    def test_morning_greeting_allowed_at_0800(self):
        d = self.policy.evaluate(evt("morning-greeting"), make_state(), make_config(), clock_at(8, 0))
        assert d.approved

    def test_morning_greeting_allowed_at_0830(self):
        d = self.policy.evaluate(evt("morning-greeting"), make_state(), make_config(), clock_at(8, 30))
        assert d.approved

    def test_other_types_not_affected_by_morning_time_gate(self):
        d = self.policy.evaluate(evt("idle-checkin"), make_state(), make_config(), clock_at(7, 0))
        # Would be blocked by quiet hours (07:00 < 07 quiet end), not too_early
        assert d.reason != "too_early"

    # cooldown

    def test_blocks_when_cooldown_active(self):
        now = clock_at(9)
        last_fired = int((now - timedelta(minutes=30)).timestamp())
        state = make_state(per_rule_last_fired={"morning-greeting": last_fired})
        d = self.policy.evaluate(evt("morning-greeting"), state, make_config(), now)
        assert not d.approved
        assert d.reason == "cooldown"

    def test_allows_after_cooldown_expires(self):
        now = clock_at(9)
        # morning-greeting cooldown is 720 min; 721 min ago = expired
        last_fired = int((now - timedelta(minutes=721)).timestamp())
        state = make_state(per_rule_last_fired={"morning-greeting": last_fired})
        d = self.policy.evaluate(evt("morning-greeting"), state, make_config(), now)
        assert d.approved

    def test_first_time_no_cooldown(self):
        # No prior fired entry → no cooldown
        d = self.policy.evaluate(evt("morning-greeting"), make_state(), make_config(), clock_at(9))
        assert d.approved

    def test_battery_cooldown_30_min(self):
        now = clock_at(14)
        last_fired = int((now - timedelta(minutes=20)).timestamp())
        state = make_state(per_rule_last_fired={"battery-low": last_fired})
        d = self.policy.evaluate(evt("battery-low", priority="medium"), state, make_config(), now)
        assert not d.approved
        assert d.reason == "cooldown"

    def test_battery_allowed_after_30_min_cooldown(self):
        now = clock_at(14)
        last_fired = int((now - timedelta(minutes=31)).timestamp())
        state = make_state(per_rule_last_fired={"battery-low": last_fired})
        d = self.policy.evaluate(evt("battery-low", priority="medium"), state, make_config(), now)
        assert d.approved

    def test_cpu_panic_short_cooldown(self):
        now = clock_at(14)
        last_fired = int((now - timedelta(minutes=3)).timestamp())
        state = make_state(per_rule_last_fired={"cpu-panic": last_fired})
        d = self.policy.evaluate(evt("cpu-panic", priority="medium"), state, make_config(), now)
        assert not d.approved
        assert d.reason == "cooldown"

    # check priority ordering — proactive_disabled before quiet_hours
    def test_proactive_disabled_checked_before_quiet_hours(self):
        d = self.policy.evaluate(
            evt("morning"), make_state(), make_config(proactive_enabled=False), clock_at(23)
        )
        assert d.reason == "proactive_disabled"


# ── Daily cap integration (simulated day) ────────────────────────────────────

class TestDailyCapIntegration:
    def test_never_exceeds_four_low_priority_utterances_in_a_day(self):
        """Acceptance criterion: max 4 proactive utterances per simulated day."""
        policy = ProactivePolicy()
        config = make_config()
        state = make_state()
        approved_count = 0

        for hour in [9, 10, 11, 13, 14, 15, 16, 17]:
            now = clock_at(hour)
            now_ts = int(now.timestamp())
            e = evt("idle-checkin", priority="low")
            decision = policy.evaluate(e, state, config, now)
            if decision.approved:
                approved_count += 1
                state = dataclasses.replace(
                    state,
                    daily_utterance_count=state.daily_utterance_count + 1,
                    last_utterance_ts=now_ts,
                    per_rule_last_fired={**state.per_rule_last_fired, "idle-checkin": now_ts},
                )

        assert approved_count <= DAILY_CAP

    def test_medium_priority_not_counted_in_daily_cap(self):
        """Medium-priority events don't count toward daily cap."""
        policy = ProactivePolicy()
        config = make_config()
        # Start with 3 low-priority count
        state = make_state(daily_utterance_count=3, daily_utterance_date=date(2026, 5, 2))

        # Medium priority (battery) should still be allowed
        d = policy.evaluate(evt("battery-low", priority="medium"), state, config, clock_at(14))
        assert d.approved

        # And a 4th low-priority should still be allowed
        d = policy.evaluate(evt("idle-checkin", priority="low"), state, config, clock_at(14))
        assert d.approved

    def test_day_boundary_resets_count(self):
        """New calendar day resets the daily cap counter."""
        policy = ProactivePolicy()
        config = make_config()
        state = make_state(daily_utterance_count=DAILY_CAP, daily_utterance_date=date(2026, 5, 1))

        # New day clock
        now = datetime(2026, 5, 2, 9, 0, 0)
        d = policy.evaluate(evt("morning-greeting", priority="low"), state, config, now)
        assert d.approved


# ── Morning greeting once-per-day ─────────────────────────────────────────────

class TestMorningGreetingOncePerDay:
    def test_first_greeting_of_day_approved(self):
        policy = ProactivePolicy()
        d = policy.evaluate(evt("morning-greeting"), make_state(), make_config(), clock_at(8, 30))
        assert d.approved

    def test_second_greeting_same_day_blocked_by_cooldown(self):
        policy = ProactivePolicy()
        # Fired at 08:05, now it's 09:00 → only 55 min ago, cooldown is 720 min
        now = clock_at(9)
        last_fired = int(clock_at(8, 5).timestamp())
        state = make_state(per_rule_last_fired={"morning-greeting": last_fired})
        d = policy.evaluate(evt("morning-greeting"), state, make_config(), now)
        assert not d.approved
        assert d.reason == "cooldown"

    def test_greeting_next_day_after_cooldown_allowed(self):
        policy = ProactivePolicy()
        # Fired yesterday at 08:05, now it's next day 08:30 → 24h+ ago, cooldown expired
        yesterday_ts = int(datetime(2026, 5, 1, 8, 5, 0).timestamp())
        state = make_state(per_rule_last_fired={"morning-greeting": yesterday_ts})
        today_clock = datetime(2026, 5, 2, 8, 30, 0)
        d = policy.evaluate(evt("morning-greeting"), state, make_config(), today_clock)
        assert d.approved


# ── Battery repeat suppression ────────────────────────────────────────────────

class TestBatteryRepeatSuppression:
    def test_battery_fired_once_per_discharge_window(self):
        policy = ProactivePolicy()
        now = clock_at(14)
        # Fired 15 min ago (cooldown is 30 min)
        last_fired = int((now - timedelta(minutes=15)).timestamp())
        state = make_state(per_rule_last_fired={"battery-low": last_fired})
        d = policy.evaluate(evt("battery-low", priority="medium"), state, make_config(), now)
        assert not d.approved
        assert d.reason == "cooldown"

    def test_battery_allowed_after_cooldown_window(self):
        policy = ProactivePolicy()
        now = clock_at(16)
        last_fired = int((now - timedelta(minutes=35)).timestamp())
        state = make_state(per_rule_last_fired={"battery-low": last_fired})
        d = policy.evaluate(evt("battery-low", priority="medium"), state, make_config(), now)
        assert d.approved

    def test_battery_never_fires_every_poll_cycle(self):
        """Simulate polling every 5 min within one 30-min cooldown window — only first fires."""
        policy = ProactivePolicy()
        config = make_config()
        state = make_state()
        approved = []

        base = clock_at(12)
        # Poll 6 times at 5-min intervals: 12:00, 12:05 … 12:25 — all within the 30-min cooldown
        for i in range(6):
            now = datetime(base.year, base.month, base.day, base.hour, i * 5, 0)
            e = evt("battery-low", priority="medium")
            d = policy.evaluate(e, state, config, now)
            if d.approved:
                approved.append(now)
                state = dataclasses.replace(
                    state,
                    per_rule_last_fired={**state.per_rule_last_fired, "battery-low": int(now.timestamp())},
                )

        assert len(approved) == 1  # only first poll fires; rest blocked by cooldown
