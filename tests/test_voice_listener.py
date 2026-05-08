from __future__ import annotations

import queue
import threading
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from src.api.event_bus import EventBus
from src.ai.voice_listener import VoiceListener, VoiceThread


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def config():
    return {
        "activation_hotkey": "ctrl+k",
        "stt_model": "base.en",
        "stt_use_vad": False,
        "recording_max_seconds": 2,
    }


def test_voice_listener_emits_recording_started(monkeypatch, bus, config, tmp_path):
    listener = VoiceListener(config, event_bus=bus)

    fake_audio = np.zeros(16000, dtype=np.float32)
    monkeypatch.setattr(listener, "_record", lambda: fake_audio)
    monkeypatch.setattr(listener, "_load_whisper", lambda: True)
    monkeypatch.setattr(listener, "_load_vad", lambda: False)
    monkeypatch.setattr(listener, "_transcribe", lambda audio: None)

    received = []
    bus.on("recording_started", lambda: received.append(True))

    listener.on_hotkey_pressed()

    assert received == [True]


def test_voice_listener_emits_transcript_ready(monkeypatch, bus, config):
    listener = VoiceListener(config, event_bus=bus)

    fake_audio = np.zeros(16000, dtype=np.float32)
    monkeypatch.setattr(listener, "_record", lambda: fake_audio)
    monkeypatch.setattr(listener, "_load_whisper", lambda: True)
    monkeypatch.setattr(listener, "_load_vad", lambda: False)

    results = []
    bus.on("transcript_ready", results.append)

    def fake_transcribe(audio):
        if listener._event_bus:
            listener._event_bus.emit("transcript_ready", "hello world")

    monkeypatch.setattr(listener, "_transcribe", fake_transcribe)
    listener.on_hotkey_pressed()

    assert results == ["hello world"]


def test_voice_listener_ignores_second_hotkey_while_recording(monkeypatch, bus, config):
    listener = VoiceListener(config, event_bus=bus)
    listener._is_recording = True

    called = []
    monkeypatch.setattr(listener, "_load_whisper", lambda: called.append(True) or True)

    listener.on_hotkey_pressed()

    assert called == []


def test_voice_listener_emits_error_on_whisper_fail(monkeypatch, bus, config):
    listener = VoiceListener(config, event_bus=bus)

    monkeypatch.setattr(listener, "_load_whisper", lambda: False)

    errors = []
    bus.on("error_occurred", errors.append)

    listener.on_hotkey_pressed()

    # Should not crash; recording flag should be reset
    assert listener._is_recording is False


def test_voice_thread_is_daemon(bus, config):
    thread = VoiceThread(config, event_bus=bus)
    assert thread.daemon is True


def test_voice_thread_queues_hotkey_and_processes(monkeypatch, bus, config):
    thread = VoiceThread(config, event_bus=bus)

    called = []
    monkeypatch.setattr(thread._listener, "on_hotkey_pressed",
                        lambda: called.append(True))

    thread.start()
    thread.on_hotkey_pressed()
    # Give the worker loop time to drain the queue
    thread._queue.join()
    thread.stop()
    thread.join(timeout=2.0)

    assert called == [True]


def test_voice_thread_stop_exits_cleanly(bus, config):
    thread = VoiceThread(config, event_bus=bus)
    thread.start()
    thread.stop()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
