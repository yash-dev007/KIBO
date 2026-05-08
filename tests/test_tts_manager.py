from __future__ import annotations

import threading
import pytest
from unittest.mock import MagicMock

from src.api.event_bus import EventBus
from src.ai.tts_manager import TTSManager, TTSThread


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def config():
    return {"tts_enabled": True}


def _make_manager(config, bus, monkeypatch):
    mgr = TTSManager(config, event_bus=bus)
    monkeypatch.setattr(mgr, "_ensure_provider", lambda: True)
    mgr._provider = MagicMock()
    return mgr


def test_speak_emits_speech_done(monkeypatch, bus, config):
    mgr = _make_manager(config, bus, monkeypatch)
    done = []
    bus.on("speech_done", lambda: done.append(True))

    mgr.speak("hello")

    assert done == [True]
    mgr._provider.speak.assert_called_once_with("hello")


def test_speak_skips_empty_text(monkeypatch, bus, config):
    mgr = _make_manager(config, bus, monkeypatch)
    done = []
    bus.on("speech_done", lambda: done.append(True))

    mgr.speak("   ")

    assert done == [True]
    mgr._provider.speak.assert_not_called()


def test_speak_disabled_emits_speech_done(bus, config):
    config["tts_enabled"] = False
    mgr = TTSManager(config, event_bus=bus)
    done = []
    bus.on("speech_done", lambda: done.append(True))

    mgr.speak("hello")

    assert done == [True]


def test_speak_chunk_queues_and_drains(monkeypatch, bus, config):
    mgr = _make_manager(config, bus, monkeypatch)
    done = []
    bus.on("speech_done", lambda: done.append(True))

    mgr.speak_chunk("sentence one")
    mgr.end_stream()

    # Wait for drain thread to finish
    if mgr._streaming_thread:
        mgr._streaming_thread.join(timeout=2.0)

    assert done == [True]
    mgr._provider.speak.assert_called_once_with("sentence one")


def test_set_silent_mode_stops_provider(monkeypatch, bus, config):
    mgr = _make_manager(config, bus, monkeypatch)

    mgr.set_silent_mode(True)

    assert mgr._silent_mode is True
    mgr._provider.stop.assert_called_once()


def test_tts_thread_is_daemon(bus, config):
    thread = TTSThread(config, event_bus=bus)
    assert thread.daemon is True


def test_tts_thread_speak_dispatches(monkeypatch, bus, config):
    thread = TTSThread(config, event_bus=bus)
    called = []
    monkeypatch.setattr(thread._manager, "speak", lambda t: called.append(t))

    thread.start()
    thread.speak("hi there")
    thread._queue.join()
    thread.stop()
    thread.join(timeout=2.0)

    assert called == ["hi there"]


def test_tts_thread_stop_exits_cleanly(bus, config):
    thread = TTSThread(config, event_bus=bus)
    thread.start()
    thread.stop()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
