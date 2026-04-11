"""
brain.py — State machine for KIBO.

Receives SensorData from SystemMonitor and query results from VoiceListener,
evaluates priority-ordered transition rules, emits BrainOutput via Qt signal.

All data structures are frozen (immutable). No Qt deps on the logic itself —
Brain subclasses QObject only for signal/slot wiring.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from config_manager import get_bundle_dir

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


# Animation folder name for each state
STATE_ANIMATION: dict[PetState, str] = {
    PetState.IDLE: "idle/stand",
    PetState.HAPPY: "actions/fly",
    PetState.TIRED: "actions/tired",
    PetState.WORKING: "actions/smartphone",
    PetState.PANICKED: "actions/spinning",
    PetState.STUDIOUS: "actions/screentap",
    PetState.SLEEPY: "actions/sleep",
    PetState.LISTENING: "idle/still",
    PetState.THINKING: "actions/bubblegum",
    PetState.TALKING: "actions/breathing",
    PetState.INTRO: "intro",
    PetState.ACTING: "acting",  # placeholder; overridden dynamically
}


@dataclass(frozen=True)
class SensorData:
    cpu_percent: float
    active_window: str
    current_hour: int
    battery_percent: Optional[float]  # None if no battery (desktop PC)


@dataclass(frozen=True)
class BrainOutput:
    state: PetState
    speech_text: Optional[str]
    animation_name: str
    loop: bool = True  # False for one-shot animations (intro, actions)


@dataclass(frozen=True)
class _Rule:
    condition: Callable[[SensorData, "Brain"], bool]
    target_state: PetState
    speech_text: Optional[str]


class Brain(QObject):
    """
    Evaluates sensor data against priority-ordered rules and emits BrainOutput.

    Priority (highest first):
      PANICKED > LISTENING > THINKING > TALKING > SLEEPY > STUDIOUS > TIRED > WORKING > HAPPY > IDLE
    """

    brain_output = Signal(BrainOutput)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        # AI states are set directly by external callers, not sensor rules
        self._ai_state: Optional[PetState] = None
        self._rules = self._build_rules()

        # Skin and action discovery
        self._skin: str = config.get("buddy_skin", "skales")
        self._available_actions: list[str] = self._discover_actions()
        self._action_bag: list[str] = []

        # Determine initial state: INTRO if assets exist, else IDLE
        self._has_intro = self._check_intro_exists()
        self._current_state: PetState = PetState.INTRO if self._has_intro else PetState.IDLE

        # Idle action timer — fires randomly every 30–60s during IDLE
        interval_min = config.get("idle_action_interval_min_s", 30)
        interval_max = config.get("idle_action_interval_max_s", 60)
        self._action_interval_min_ms = int(interval_min * 1000)
        self._action_interval_max_ms = int(interval_max * 1000)

        self._action_timer = QTimer(self)
        self._action_timer.setSingleShot(True)
        self._action_timer.timeout.connect(self._on_action_timer_fired)

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
            ),
            _Rule(
                condition=lambda s, _: s.current_hour >= sleepy_hour,
                target_state=PetState.SLEEPY,
                speech_text="Getting sleepy...",
            ),
            _Rule(
                condition=lambda s, _: any(w in s.active_window.lower() for w in studious_windows),
                target_state=PetState.STUDIOUS,
                speech_text="Let's code!",
            ),
            _Rule(
                condition=lambda s, _: (
                    s.battery_percent is not None and s.battery_percent < battery_thresh
                ),
                target_state=PetState.TIRED,
                speech_text="Running low on battery...",
            ),
            _Rule(
                condition=lambda s, _: s.cpu_percent > 50,
                target_state=PetState.WORKING,
                speech_text=None,
            ),
        ]

    # ------------------------------------------------------------------
    # Action discovery
    # ------------------------------------------------------------------

    def _discover_actions(self) -> list[str]:
        """Scan assets/animations/ for {skin}_action_{name}/ folders."""
        prefix = f"{self._skin}_action_"
        actions = []
        if ASSETS_DIR.exists():
            for d in ASSETS_DIR.iterdir():
                if d.is_dir() and d.name.startswith(prefix):
                    clip_name = d.name[len(prefix):]
                    if clip_name:
                        actions.append(clip_name)
        if actions:
            logger.info("Discovered %d action clips for skin '%s': %s",
                        len(actions), self._skin, actions)
        else:
            logger.info("No action clips found for skin '%s'.", self._skin)
        return actions

    def _check_intro_exists(self) -> bool:
        """Check if any intro animation folder exists for the current skin."""
        prefix = f"{self._skin}_intro_"
        if ASSETS_DIR.exists():
            for d in ASSETS_DIR.iterdir():
                if d.is_dir() and d.name.startswith(prefix):
                    if any(d.glob("frame_*.png")):
                        return True
        # Also check plain "intro" folder (placeholder)
        intro_dir = ASSETS_DIR / "intro"
        if intro_dir.exists() and any(intro_dir.glob("frame_*.png")):
            return True
        return False

    def _pick_action(self) -> str:
        """Pick a random action using shuffled-bag (no repeats until all seen)."""
        if not self._action_bag:
            self._action_bag = list(self._available_actions)
            random.shuffle(self._action_bag)
        return self._action_bag.pop()

    # ------------------------------------------------------------------
    # Idle action timer
    # ------------------------------------------------------------------

    def _start_action_timer(self) -> None:
        """Start the idle action timer with a random interval."""
        if not self._available_actions:
            return
        interval = random.randint(self._action_interval_min_ms, self._action_interval_max_ms)
        self._action_timer.start(interval)

    def _stop_action_timer(self) -> None:
        self._action_timer.stop()

    def _on_action_timer_fired(self) -> None:
        """Timer expired during IDLE — play a random action clip."""
        if self._current_state != PetState.IDLE:
            return
        if self._ai_state is not None:
            return
        if not self._available_actions:
            return

        clip_name = self._pick_action()
        self._current_state = PetState.ACTING
        animation = f"actions/{clip_name}"
        output = BrainOutput(
            state=PetState.ACTING,
            speech_text=None,
            animation_name=animation,
            loop=False,
        )
        self.brain_output.emit(output)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def get_initial_output(self) -> BrainOutput:
        """Return the initial BrainOutput for startup."""
        if self._has_intro:
            # Pick a random intro clip
            prefix = f"{self._skin}_intro_"
            intro_clips = []
            if ASSETS_DIR.exists():
                for d in ASSETS_DIR.iterdir():
                    if d.is_dir() and d.name.startswith(prefix):
                        intro_clips.append(d.name[len(prefix):])
            if intro_clips:
                clip = random.choice(intro_clips)
                anim_name = f"intro/{clip}"
            else:
                anim_name = "intro"
            return BrainOutput(
                state=PetState.INTRO,
                speech_text=None,
                animation_name=anim_name,
                loop=False,
            )
        return BrainOutput(
            state=PetState.IDLE,
            speech_text=None,
            animation_name=STATE_ANIMATION[PetState.IDLE],
        )

    # ------------------------------------------------------------------
    # Slots called by AnimationController (via UIManager)
    # ------------------------------------------------------------------

    def on_animation_done(self) -> None:
        """One-shot animation finished — transition back to IDLE."""
        if self._current_state == PetState.INTRO:
            logger.info("Intro finished → IDLE")
            self._current_state = PetState.IDLE
            output = BrainOutput(
                state=PetState.IDLE,
                speech_text=None,
                animation_name=STATE_ANIMATION[PetState.IDLE],
            )
            self.brain_output.emit(output)
            self._start_action_timer()

        elif self._current_state == PetState.ACTING:
            logger.info("Action clip finished → IDLE")
            self._current_state = PetState.IDLE
            output = BrainOutput(
                state=PetState.IDLE,
                speech_text=None,
                animation_name=STATE_ANIMATION[PetState.IDLE],
            )
            self.brain_output.emit(output)
            self._start_action_timer()

    # ------------------------------------------------------------------
    # Slots called by SystemMonitor
    # ------------------------------------------------------------------

    def on_sensor_update(self, sensor_data: SensorData) -> None:
        """Evaluate rules and emit output if state changed."""
        # AI states and one-shot states take priority
        if self._ai_state is not None:
            return
        if self._current_state in (PetState.INTRO, PetState.ACTING):
            return

        new_state = PetState.IDLE
        speech: Optional[str] = None

        for rule in self._rules:
            if rule.condition(sensor_data, self):
                new_state = rule.target_state
                speech = rule.speech_text
                break

        # Only emit speech on transitions; always emit output so UI stays current
        if new_state == self._current_state:
            speech = None

        self._current_state = new_state
        output = BrainOutput(
            state=new_state,
            speech_text=speech,
            animation_name=STATE_ANIMATION[new_state],
        )
        self.brain_output.emit(output)

    # ------------------------------------------------------------------
    # Slots called by VoiceListener / AIClient
    # ------------------------------------------------------------------

    def on_listening_started(self) -> None:
        self._stop_action_timer()
        self._set_ai_state(PetState.LISTENING, "Yeah?")

    def on_thinking_started(self) -> None:
        self._set_ai_state(PetState.THINKING, "Hmm...")

    def on_talking_started(self, response_text: str) -> None:
        self._set_ai_state(PetState.TALKING, response_text)

    def on_ai_done(self) -> None:
        """Return to sensor-driven state after AI interaction completes."""
        self._ai_state = None
        self._current_state = PetState.IDLE
        output = BrainOutput(
            state=PetState.IDLE,
            speech_text=None,
            animation_name=STATE_ANIMATION[PetState.IDLE],
        )
        self.brain_output.emit(output)
        self._start_action_timer()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _set_ai_state(self, state: PetState, speech: Optional[str]) -> None:
        self._ai_state = state
        self._current_state = state
        output = BrainOutput(
            state=state,
            speech_text=speech,
            animation_name=STATE_ANIMATION[state],
        )
        self.brain_output.emit(output)

    @property
    def current_state(self) -> PetState:
        return self._current_state
