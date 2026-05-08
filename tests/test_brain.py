"""tests/test_brain.py — Unit tests for the Brain state machine."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.api.event_bus import EventBus
from src.ai.brain import Brain, PetState, SensorData, BrainOutput, STATE_ANIMATION

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
    return SensorData(cpu_percent=cpu, active_window=window, current_hour=hour, battery_percent=battery)


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def brain(bus):
    b = Brain(CONFIG, event_bus=bus)
    b._current_state = PetState.IDLE
    b._has_intro = False
    return b


def collect_outputs(brain, bus, sensor_data):
    outputs = []
    handler = outputs.append
    bus.on("brain_output", handler)
    brain.on_sensor_update(sensor_data)
    bus.off("brain_output", handler)
    return outputs


class TestStateTransitions:
    def test_default_state_is_idle(self, brain):
        assert brain.current_state == PetState.IDLE

    def test_high_cpu_triggers_panicked(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(cpu=90.0))
        assert len(outputs) == 1
        assert outputs[0].state == PetState.PANICKED

    def test_sleepy_hour_triggers_sleepy(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(hour=23))
        assert len(outputs) == 1
        assert outputs[0].state == PetState.SLEEPY

    def test_vscode_triggers_studious(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(window="Visual Studio Code - main.py"))
        assert len(outputs) == 1
        assert outputs[0].state == PetState.STUDIOUS

    def test_low_battery_triggers_tired(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(battery=10.0))
        assert len(outputs) == 1
        assert outputs[0].state == PetState.TIRED

    def test_medium_cpu_triggers_working(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(cpu=60.0))
        assert len(outputs) == 1
        assert outputs[0].state == PetState.WORKING

    def test_idle_when_no_triggers(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(cpu=40.0, hour=10))
        assert outputs == []
        assert brain.current_state == PetState.IDLE


class TestPriority:
    def test_panicked_beats_sleepy(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(cpu=95.0, hour=23))
        assert outputs[0].state == PetState.PANICKED

    def test_panicked_beats_studious(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(cpu=95.0, window="Visual Studio Code"))
        assert outputs[0].state == PetState.PANICKED

    def test_sleepy_beats_studious(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(hour=23, window="Visual Studio Code"))
        assert outputs[0].state == PetState.SLEEPY


class TestSpeechOnTransitionOnly:
    def test_speech_emitted_on_transition(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(cpu=90.0))
        assert outputs[0].speech_text is not None

    def test_no_speech_on_same_state(self, brain, bus):
        collect_outputs(brain, bus, make_sensor(cpu=90.0))
        outputs = collect_outputs(brain, bus, make_sensor(cpu=91.0))
        assert outputs == []
        assert brain.current_state == PetState.PANICKED

    def test_animation_name_matches_state(self, brain, bus):
        outputs = collect_outputs(brain, bus, make_sensor(cpu=90.0))
        assert outputs[0].animation_name == STATE_ANIMATION[PetState.PANICKED]


class TestAIStates:
    def test_listening_state(self, brain, bus):
        outputs = []
        bus.on("brain_output", outputs.append)
        brain.on_listening_started()
        bus.off("brain_output", outputs.append)
        assert outputs[0].state == PetState.LISTENING
        assert outputs[0].speech_text == "Yeah?"

    def test_thinking_state(self, brain, bus):
        outputs = []
        bus.on("brain_output", outputs.append)
        brain.on_thinking_started()
        bus.off("brain_output", outputs.append)
        assert outputs[0].state == PetState.THINKING

    def test_ai_done_returns_to_idle(self, brain, bus):
        brain.on_listening_started()
        outputs = []
        bus.on("brain_output", outputs.append)
        brain.on_ai_done()
        bus.off("brain_output", outputs.append)
        assert outputs[0].state == PetState.IDLE

    def test_sensor_ignored_during_ai(self, brain, bus):
        brain.on_thinking_started()
        outputs = collect_outputs(brain, bus, make_sensor(cpu=99.0))
        assert len(outputs) == 0


class TestIntroState:
    def test_initial_output_intro_when_assets_exist(self, bus):
        b = Brain(CONFIG, event_bus=bus)
        b._has_intro = True
        b._current_state = PetState.INTRO
        output = b.get_initial_output()
        assert output.state == PetState.INTRO
        assert output.loop is False

    def test_initial_output_idle_when_no_intro(self, bus):
        b = Brain(CONFIG, event_bus=bus)
        b._has_intro = False
        b._current_state = PetState.IDLE
        output = b.get_initial_output()
        assert output.state == PetState.IDLE
        assert output.loop is True

    def test_on_animation_done_intro_to_idle(self, brain, bus):
        brain._current_state = PetState.INTRO
        outputs = []
        bus.on("brain_output", outputs.append)
        brain.on_animation_done()
        bus.off("brain_output", outputs.append)
        assert len(outputs) == 1
        assert outputs[0].state == PetState.IDLE

    def test_sensor_ignored_during_intro(self, brain, bus):
        brain._current_state = PetState.INTRO
        outputs = collect_outputs(brain, bus, make_sensor(cpu=99.0))
        assert len(outputs) == 0


class TestActingState:
    def test_on_animation_done_acting_to_idle(self, brain, bus):
        brain._current_state = PetState.ACTING
        outputs = []
        bus.on("brain_output", outputs.append)
        brain.on_animation_done()
        bus.off("brain_output", outputs.append)
        assert len(outputs) == 1
        assert outputs[0].state == PetState.IDLE

    def test_sensor_ignored_during_acting(self, brain, bus):
        brain._current_state = PetState.ACTING
        outputs = collect_outputs(brain, bus, make_sensor(cpu=99.0))
        assert len(outputs) == 0

    def test_pick_action_no_repeat_until_all_seen(self, brain):
        brain._available_actions = ["a", "b", "c"]
        brain._action_bag = []
        seen = [brain._pick_action() for _ in range(3)]
        assert sorted(seen) == ["a", "b", "c"]

    def test_pick_action_reshuffles_when_empty(self, brain):
        brain._available_actions = ["x", "y"]
        brain._action_bag = []
        brain._pick_action()
        brain._pick_action()
        result = brain._pick_action()
        assert result in ("x", "y")

    def test_action_timer_fires_acting_state(self, brain, bus):
        brain._available_actions = ["stretch"]
        brain._action_bag = []
        brain._current_state = PetState.IDLE

        outputs = []
        bus.on("brain_output", outputs.append)
        brain._on_action_timer_fired()
        bus.off("brain_output", outputs.append)

        assert len(outputs) == 1
        assert outputs[0].state == PetState.ACTING
        assert outputs[0].animation_name == "action/stretch"
        assert outputs[0].loop is False

    def test_action_timer_skipped_during_ai(self, brain, bus):
        brain._available_actions = ["stretch"]
        brain._ai_state = PetState.THINKING
        brain._current_state = PetState.THINKING

        outputs = []
        bus.on("brain_output", outputs.append)
        brain._on_action_timer_fired()
        bus.off("brain_output", outputs.append)

        assert len(outputs) == 0
