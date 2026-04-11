"""
tests/test_brain.py — Unit tests for the Brain state machine.

Tests all transitions, priority order, speech-on-transition-only behavior,
and new INTRO/ACTING states with idle action timer.
No Qt event loop needed — we call on_sensor_update directly and inspect emitted signals.
"""

import pytest
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication

# QApplication must exist before importing Brain (PySide6 requirement)
@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


CONFIG = {
    "cpu_panic_threshold": 80,
    "sleepy_hour": 23,
    "battery_tired_threshold": 20,
    "studious_windows": ["Visual Studio Code", "code"],
    "buddy_skin": "skales",
    "idle_action_interval_min_s": 30,
    "idle_action_interval_max_s": 60,
}


def make_sensor(cpu=0.0, window="", hour=12, battery=100.0):
    from brain import SensorData
    return SensorData(cpu_percent=cpu, active_window=window, current_hour=hour, battery_percent=battery)


@pytest.fixture
def brain(qt_app):
    from brain import Brain
    b = Brain(CONFIG)
    # Force to IDLE for most tests (skip INTRO)
    from brain import PetState
    b._current_state = PetState.IDLE
    b._has_intro = False
    return b


def collect_outputs(brain, sensor_data):
    """Call on_sensor_update and collect all emitted BrainOutput objects."""
    outputs = []
    brain.brain_output.connect(lambda o: outputs.append(o))
    brain.on_sensor_update(sensor_data)
    brain.brain_output.disconnect()
    return outputs


class TestStateTransitions:
    def test_default_state_is_idle(self, brain):
        from brain import PetState
        assert brain.current_state == PetState.IDLE

    def test_high_cpu_triggers_panicked(self, brain):
        from brain import PetState
        outputs = collect_outputs(brain, make_sensor(cpu=90.0))
        assert len(outputs) == 1
        assert outputs[0].state == PetState.PANICKED

    def test_sleepy_hour_triggers_sleepy(self, brain):
        from brain import PetState
        outputs = collect_outputs(brain, make_sensor(hour=23))
        assert len(outputs) == 1
        assert outputs[0].state == PetState.SLEEPY

    def test_vscode_triggers_studious(self, brain):
        from brain import PetState
        outputs = collect_outputs(brain, make_sensor(window="Visual Studio Code - main.py"))
        assert len(outputs) == 1
        assert outputs[0].state == PetState.STUDIOUS

    def test_low_battery_triggers_tired(self, brain):
        from brain import PetState
        outputs = collect_outputs(brain, make_sensor(battery=10.0))
        assert len(outputs) == 1
        assert outputs[0].state == PetState.TIRED

    def test_medium_cpu_triggers_working(self, brain):
        from brain import PetState
        outputs = collect_outputs(brain, make_sensor(cpu=60.0))
        assert len(outputs) == 1
        assert outputs[0].state == PetState.WORKING

    def test_idle_when_no_triggers(self, brain):
        from brain import PetState
        outputs = collect_outputs(brain, make_sensor(cpu=10.0, hour=10))
        assert outputs[0].state == PetState.IDLE


class TestPriority:
    def test_panicked_beats_sleepy(self, brain):
        from brain import PetState
        # Both conditions true: CPU high AND late hour
        outputs = collect_outputs(brain, make_sensor(cpu=95.0, hour=23))
        assert outputs[0].state == PetState.PANICKED

    def test_panicked_beats_studious(self, brain):
        from brain import PetState
        outputs = collect_outputs(brain, make_sensor(cpu=95.0, window="Visual Studio Code"))
        assert outputs[0].state == PetState.PANICKED

    def test_sleepy_beats_studious(self, brain):
        from brain import PetState
        outputs = collect_outputs(brain, make_sensor(hour=23, window="Visual Studio Code"))
        assert outputs[0].state == PetState.SLEEPY


class TestSpeechOnTransitionOnly:
    def test_speech_emitted_on_transition(self, brain):
        from brain import PetState
        # First trigger: transition from IDLE -> PANICKED, speech expected
        outputs = collect_outputs(brain, make_sensor(cpu=90.0))
        assert outputs[0].speech_text is not None

    def test_no_speech_on_same_state(self, brain):
        from brain import PetState
        # Trigger PANICKED twice in a row — second should have no speech
        collect_outputs(brain, make_sensor(cpu=90.0))  # transition
        outputs = collect_outputs(brain, make_sensor(cpu=91.0))  # same state
        assert outputs[0].speech_text is None

    def test_animation_name_matches_state(self, brain):
        from brain import PetState, STATE_ANIMATION
        outputs = collect_outputs(brain, make_sensor(cpu=90.0))
        assert outputs[0].animation_name == STATE_ANIMATION[PetState.PANICKED]


class TestAIStates:
    def test_listening_state(self, brain):
        from brain import PetState
        outputs = []
        brain.brain_output.connect(lambda o: outputs.append(o))
        brain.on_listening_started()
        brain.brain_output.disconnect()
        assert outputs[0].state == PetState.LISTENING
        assert outputs[0].speech_text == "Yeah?"

    def test_thinking_state(self, brain):
        from brain import PetState
        outputs = []
        brain.brain_output.connect(lambda o: outputs.append(o))
        brain.on_thinking_started()
        brain.brain_output.disconnect()
        assert outputs[0].state == PetState.THINKING

    def test_ai_done_returns_to_idle(self, brain):
        from brain import PetState
        brain.on_listening_started()
        outputs = []
        brain.brain_output.connect(lambda o: outputs.append(o))
        brain.on_ai_done()
        brain.brain_output.disconnect()
        assert outputs[0].state == PetState.IDLE

    def test_sensor_ignored_during_ai(self, brain):
        from brain import PetState
        brain.on_thinking_started()
        outputs = []
        brain.brain_output.connect(lambda o: outputs.append(o))
        brain.on_sensor_update(make_sensor(cpu=99.0))
        brain.brain_output.disconnect()
        # Sensor should be ignored while AI state is active
        assert len(outputs) == 0


class TestIntroState:
    def test_initial_output_intro_when_assets_exist(self, qt_app):
        from brain import Brain, PetState
        b = Brain(CONFIG)
        b._has_intro = True
        b._current_state = PetState.INTRO
        output = b.get_initial_output()
        assert output.state == PetState.INTRO
        assert output.loop is False

    def test_initial_output_idle_when_no_intro(self, qt_app):
        from brain import Brain, PetState
        b = Brain(CONFIG)
        b._has_intro = False
        b._current_state = PetState.IDLE
        output = b.get_initial_output()
        assert output.state == PetState.IDLE
        assert output.loop is True

    def test_on_animation_done_intro_to_idle(self, brain):
        from brain import PetState
        brain._current_state = PetState.INTRO
        outputs = []
        brain.brain_output.connect(lambda o: outputs.append(o))
        brain.on_animation_done()
        brain.brain_output.disconnect()
        assert len(outputs) == 1
        assert outputs[0].state == PetState.IDLE

    def test_sensor_ignored_during_intro(self, brain):
        from brain import PetState
        brain._current_state = PetState.INTRO
        outputs = []
        brain.brain_output.connect(lambda o: outputs.append(o))
        brain.on_sensor_update(make_sensor(cpu=99.0))
        brain.brain_output.disconnect()
        assert len(outputs) == 0


class TestActingState:
    def test_on_animation_done_acting_to_idle(self, brain):
        from brain import PetState
        brain._current_state = PetState.ACTING
        outputs = []
        brain.brain_output.connect(lambda o: outputs.append(o))
        brain.on_animation_done()
        brain.brain_output.disconnect()
        assert len(outputs) == 1
        assert outputs[0].state == PetState.IDLE

    def test_sensor_ignored_during_acting(self, brain):
        from brain import PetState
        brain._current_state = PetState.ACTING
        outputs = []
        brain.brain_output.connect(lambda o: outputs.append(o))
        brain.on_sensor_update(make_sensor(cpu=99.0))
        brain.brain_output.disconnect()
        assert len(outputs) == 0

    def test_pick_action_no_repeat_until_all_seen(self, brain):
        """Shuffled bag: no repeat until all actions have been played."""
        brain._available_actions = ["a", "b", "c"]
        brain._action_bag = []

        seen = []
        for _ in range(3):
            seen.append(brain._pick_action())

        # All 3 unique actions should have been seen
        assert sorted(seen) == ["a", "b", "c"]

    def test_pick_action_reshuffles_when_empty(self, brain):
        """After all actions seen, bag refills."""
        brain._available_actions = ["x", "y"]
        brain._action_bag = []

        # Drain first bag
        brain._pick_action()
        brain._pick_action()
        # Bag should be empty, next pick refills
        result = brain._pick_action()
        assert result in ("x", "y")

    def test_action_timer_fires_acting_state(self, brain):
        from brain import PetState
        brain._available_actions = ["stretch"]
        brain._action_bag = []
        brain._current_state = PetState.IDLE

        outputs = []
        brain.brain_output.connect(lambda o: outputs.append(o))
        brain._on_action_timer_fired()
        brain.brain_output.disconnect()

        assert len(outputs) == 1
        assert outputs[0].state == PetState.ACTING
        assert outputs[0].animation_name == "actions/stretch"
        assert outputs[0].loop is False

    def test_action_timer_skipped_during_ai(self, brain):
        from brain import PetState
        brain._available_actions = ["stretch"]
        brain._ai_state = PetState.THINKING
        brain._current_state = PetState.THINKING

        outputs = []
        brain.brain_output.connect(lambda o: outputs.append(o))
        brain._on_action_timer_fired()
        brain.brain_output.disconnect()

        assert len(outputs) == 0
