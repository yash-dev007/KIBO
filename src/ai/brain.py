"""
brain.py — State machine for KIBO.

Receives SensorData from SystemMonitor and query results from VoiceListener,
evaluates priority-ordered transition rules, emits BrainOutput via EventBus.

All data structures are frozen (immutable). No Qt deps on the logic itself.
"""
from __future__ import annotations

import logging
import random
import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

from src.core.config_manager import get_bundle_dir

logger = logging.getLogger(__name__)

ASSETS_DIR = get_bundle_dir() / "assets" / "animations"


class PetState(Enum):
    IDLE = auto()
    HAPPY = auto()
    TIRED = auto()
    WORKING = auto()
    PANICKED = auto()
    STUDIOUS = auto()
    SLEEPY = auto()
    LISTENING = auto()
    THINKING = auto()
    TALKING = auto()
    INTRO = auto()
    ACTING = auto()


STATE_ANIMATION: dict[PetState, str] = {
    PetState.IDLE: "idle/stand",
    PetState.HAPPY: "idle/stand",
    PetState.TIRED: "action/tired",
    PetState.WORKING: "action/smartphone",
    PetState.PANICKED: "action/spinning",
    PetState.STUDIOUS: "action/screentap",
    PetState.SLEEPY: "action/sleep",
    PetState.LISTENING: "idle/still",
    PetState.THINKING: "action/bubblegum",
    PetState.TALKING: "action/breathing",
    PetState.INTRO: "intro/spawn",
    PetState.ACTING: "action/placeholder",
}


@dataclass(frozen=True)
class SensorData:
    cpu_percent: float
    active_window: str
    current_hour: int
    battery_percent: Optional[float]


@dataclass(frozen=True)
class BrainOutput:
    state: PetState
    speech_text: Optional[str]
    animation_name: str
    loop: bool = True


@dataclass(frozen=True)
class _Rule:
    condition: Callable[[SensorData, "Brain"], bool]
    target_state: PetState
    speech_text: Optional[str]
    notification_type: Optional[str] = None


class Brain:
    """
    Evaluates sensor data against priority-ordered rules and emits BrainOutput.

    Priority (highest first):
      PANICKED > LISTENING > THINKING > TALKING > SLEEPY > STUDIOUS > TIRED > WORKING > HAPPY > IDLE
    """

    def __init__(self, config: dict, router=None, event_bus=None) -> None:
        self._config = config
        self._router = router
        self._event_bus = event_bus
        self._ai_state: Optional[PetState] = None
        self._rules = self._build_rules()
        self._lock = threading.RLock()

        self._skin: str = config.get("buddy_skin", "skales")
        self._available_actions: list[str] = self._discover_actions()
        self._action_bag: list[str] = []
        self._available_idles: list[str] = self._discover_idles()

        self._has_intro = self._check_intro_exists()
        self._current_state: PetState = PetState.INTRO if self._has_intro else PetState.IDLE

        interval_min = config.get("idle_action_interval_min_s", 30)
        interval_max = config.get("idle_action_interval_max_s", 60)
        self._action_interval_min_ms = int(interval_min * 1000)
        self._action_interval_max_ms = int(interval_max * 1000)
        self._action_timer: Optional[threading.Timer] = None
        self._timer_lock = threading.Lock()

    def _build_rules(self) -> list[_Rule]:
        cfg = self._config
        cpu_thresh = cfg["cpu_panic_threshold"]
        sleepy_hour = cfg["sleepy_hour"]
        battery_thresh = cfg["battery_tired_threshold"]
        studious_windows: list[str] = [w.lower() for w in cfg["studious_windows"]]

        return [
            _Rule(
                condition=lambda s, _: s.cpu_percent > cpu_thresh,
                target_state=PetState.PANICKED,
                speech_text="So many processes!",
                notification_type="cpu-panic",
            ),
            _Rule(
                condition=lambda s, _: s.current_hour >= sleepy_hour,
                target_state=PetState.SLEEPY,
                speech_text="Getting sleepy...",
                notification_type="sleepy",
            ),
            _Rule(
                condition=lambda s, _: any(w in s.active_window.lower() for w in studious_windows),
                target_state=PetState.STUDIOUS,
                speech_text="Let's code!",
                notification_type="studious",
            ),
            _Rule(
                condition=lambda s, _: (
                    s.battery_percent is not None and s.battery_percent < battery_thresh
                ),
                target_state=PetState.TIRED,
                speech_text="Running low on battery...",
                notification_type="battery-low",
            ),
            _Rule(
                condition=lambda s, _: s.cpu_percent > 50,
                target_state=PetState.WORKING,
                speech_text=None,
            ),
            _Rule(
                condition=lambda s, _: (
                    s.cpu_percent < 30
                    and (s.battery_percent is None or s.battery_percent > 50)
                    and 8 <= s.current_hour < 20
                ),
                target_state=PetState.HAPPY,
                speech_text=None,
            ),
        ]

    # ── Action/Idle discovery ────────────────────────────────────────────

    def _discover_idles(self) -> list[str]:
        idles = []
        idle_dir = ASSETS_DIR / self._skin / "idle"
        if idle_dir.exists() and idle_dir.is_dir():
            for p in idle_dir.iterdir():
                if p.is_file() and p.name.endswith(".webm"):
                    idles.append(p.stem)
        return sorted(list(set(idles)))

    def _get_anim_for_state(self, state: PetState) -> str:
        base_anim = STATE_ANIMATION.get(state, "idle/stand")
        if "/" not in base_anim:
            return base_anim
        category, clip = base_anim.split("/", 1)
        path = ASSETS_DIR / self._skin / category / f"{clip}.webm"
        if path.is_file():
            return base_anim
        if category == "idle" and self._available_idles:
            return f"idle/{self._available_idles[0]}"
        elif category == "action" and self._available_actions:
            return f"action/{self._pick_action()}"
        return f"idle/{self._available_idles[0]}" if self._available_idles else "idle/idle"

    def _discover_actions(self) -> list[str]:
        actions = []
        action_dir = ASSETS_DIR / self._skin / "action"
        if action_dir.exists() and action_dir.is_dir():
            for p in action_dir.iterdir():
                if p.is_file() and p.name.endswith(".webm"):
                    actions.append(p.stem)
                elif p.is_dir() and any(p.glob("frame_*.png")):
                    actions.append(p.name)
        actions = sorted(list(set(actions)))
        if actions:
            logger.info("Discovered %d action clips for skin '%s': %s", len(actions), self._skin, actions)
        else:
            logger.info("No action clips found for skin '%s'.", self._skin)
        return actions

    def _check_intro_exists(self) -> bool:
        intro_dir = ASSETS_DIR / self._skin / "intro"
        if intro_dir.exists() and intro_dir.is_dir():
            return any(p.name.endswith(".webm") for p in intro_dir.iterdir())
        return False

    def _pick_action(self) -> str:
        if not self._available_actions:
            return "placeholder"
        if not self._action_bag:
            self._action_bag = list(self._available_actions)
            random.shuffle(self._action_bag)
        return self._action_bag.pop()

    # ── Action timer ─────────────────────────────────────────────────────

    def _start_action_timer(self) -> None:
        if not self._available_actions:
            return
        interval_s = random.randint(
            self._action_interval_min_ms, self._action_interval_max_ms
        ) / 1000.0
        with self._timer_lock:
            if self._action_timer is not None:
                self._action_timer.cancel()
            self._action_timer = threading.Timer(interval_s, self._on_action_timer_fired)
            self._action_timer.daemon = True
            self._action_timer.start()

    def _stop_action_timer(self) -> None:
        with self._timer_lock:
            if self._action_timer is not None:
                self._action_timer.cancel()
                self._action_timer = None

    def _on_action_timer_fired(self) -> None:
        with self._lock:
            if self._ai_state is not None or self._current_state not in (PetState.IDLE, PetState.HAPPY):
                self._start_action_timer()
                return
            if not self._available_actions:
                return
            clip_name = self._pick_action()
            self._current_state = PetState.ACTING
        animation = f"action/{clip_name}"
        output = BrainOutput(state=PetState.ACTING, speech_text=None, animation_name=animation, loop=False)
        self._emit(output)

    # ── Startup ──────────────────────────────────────────────────────────

    def get_initial_output(self) -> BrainOutput:
        if self._has_intro:
            intro_clips = []
            intro_dir = ASSETS_DIR / self._skin / "intro"
            if intro_dir.exists() and intro_dir.is_dir():
                for p in intro_dir.iterdir():
                    if p.is_file() and p.name.endswith(".webm"):
                        intro_clips.append(p.stem)
            if intro_clips:
                clip = random.choice(intro_clips)
                anim_name = f"intro/{clip}"
            else:
                anim_name = "intro/spawn"
            return BrainOutput(state=PetState.INTRO, speech_text=None, animation_name=anim_name, loop=False)
        return BrainOutput(
            state=PetState.IDLE,
            speech_text=None,
            animation_name=self._get_anim_for_state(PetState.IDLE),
        )

    # ── Event handlers ────────────────────────────────────────────────────

    def on_animation_done(self) -> None:
        with self._lock:
            if self._current_state == PetState.INTRO:
                logger.info("Intro finished → IDLE")
                self._current_state = PetState.IDLE
                output = BrainOutput(
                    state=PetState.IDLE,
                    speech_text=None,
                    animation_name=self._get_anim_for_state(PetState.IDLE),
                )
            elif self._current_state == PetState.ACTING:
                logger.info("Action clip finished → IDLE")
                self._current_state = PetState.IDLE
                output = BrainOutput(
                    state=PetState.IDLE,
                    speech_text=None,
                    animation_name=self._get_anim_for_state(PetState.IDLE),
                )
            else:
                return
        self._emit(output)
        self._start_action_timer()

    def on_sensor_update(self, sensor_data: SensorData) -> None:
        with self._lock:
            if self._ai_state is not None:
                return
            if self._current_state in (PetState.INTRO, PetState.ACTING):
                return

            new_state = PetState.IDLE
            speech: Optional[str] = None
            notification_type: Optional[str] = None

            for rule in self._rules:
                if rule.condition(sensor_data, self):
                    new_state = rule.target_state
                    speech = rule.speech_text
                    notification_type = rule.notification_type
                    break

            if new_state == self._current_state:
                speech = None

            if new_state == self._current_state and speech is None:
                return

            if speech and self._router and notification_type:
                priority = "medium" if notification_type in ("cpu-panic", "battery-low") else "low"
                if not self._router.route(notification_type, speech, priority):
                    speech = None

            self._current_state = new_state
            output = BrainOutput(
                state=new_state,
                speech_text=speech,
                animation_name=self._get_anim_for_state(new_state),
            )
        self._emit(output)

    def on_listening_started(self) -> None:
        with self._lock:
            if self._ai_state in (PetState.LISTENING, PetState.THINKING, PetState.TALKING):
                return
        self._stop_action_timer()
        self._set_ai_state(PetState.LISTENING, "Yeah?")

    def on_thinking_started(self) -> None:
        self._set_ai_state(PetState.THINKING, "Hmm...")

    def on_talking_started(self, response_text: str) -> None:
        self._set_ai_state(PetState.TALKING, response_text)

    def on_ai_done(self) -> None:
        with self._lock:
            self._ai_state = None
            self._current_state = PetState.IDLE
            output = BrainOutput(
                state=PetState.IDLE,
                speech_text=None,
                animation_name=self._get_anim_for_state(PetState.IDLE),
            )
        self._emit(output)
        self._start_action_timer()

    def on_config_changed(self, new_config: dict) -> None:
        with self._lock:
            old_skin = self._skin
            new_skin = new_config.get("buddy_skin", "skales")
            self._config = new_config
            if old_skin != new_skin:
                self._skin = new_skin
                self._available_actions = self._discover_actions()
                self._action_bag = []
                self._available_idles = self._discover_idles()
                self._has_intro = self._check_intro_exists()
                logger.info("Brain updated skin from '%s' to '%s'", old_skin, new_skin)
                self._current_state = PetState.IDLE
                self._ai_state = None
                output = BrainOutput(
                    state=PetState.IDLE,
                    speech_text=None,
                    animation_name=self._get_anim_for_state(PetState.IDLE),
                )
                self._emit(output)
                self._start_action_timer()

    # ── Internal ──────────────────────────────────────────────────────────

    def _set_ai_state(self, state: PetState, speech: Optional[str]) -> None:
        with self._lock:
            self._ai_state = state
            self._current_state = state
            if state in (PetState.THINKING, PetState.TALKING):
                anim_name = f"action/{self._pick_action()}"
            else:
                anim_name = self._get_anim_for_state(state)
            output = BrainOutput(state=state, speech_text=speech, animation_name=anim_name)
        self._emit(output)

    def _emit(self, output: BrainOutput) -> None:
        if self._event_bus:
            self._event_bus.emit("brain_output", output)

    @property
    def current_state(self) -> PetState:
        return self._current_state
