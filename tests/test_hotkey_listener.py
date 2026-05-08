from __future__ import annotations

import threading
import pytest
from src.api.event_bus import EventBus
from src.system.hotkey_listener import HotkeyListener, HotkeyThread


@pytest.fixture
def bus():
    return EventBus()


def _patch_keyboard(monkeypatch):
    hotkeys: dict[str, object] = {}
    monkeypatch.setattr("src.system.hotkey_listener.keyboard.add_hotkey",
                        lambda key, cb: hotkeys.update({key: cb}))
    monkeypatch.setattr("src.system.hotkey_listener.keyboard.unhook_all", lambda: None)
    return hotkeys


def test_hotkey_listener_emits_hotkey_pressed(monkeypatch, bus):
    config = {"activation_hotkey": "ctrl+k", "clip_hotkey": "ctrl+alt+k"}
    hotkeys = _patch_keyboard(monkeypatch)

    listener = HotkeyListener(config, event_bus=bus)
    received = []
    bus.on("hotkey_pressed", lambda: received.append(True))

    listener.start_listening()
    hotkeys["ctrl+k"]()

    assert received == [True]


def test_hotkey_listener_emits_clip_hotkey_pressed(monkeypatch, bus):
    config = {"activation_hotkey": "ctrl+k", "clip_hotkey": "ctrl+alt+k"}
    hotkeys = _patch_keyboard(monkeypatch)

    listener = HotkeyListener(config, event_bus=bus)
    received = []
    bus.on("clip_hotkey_pressed", lambda: received.append(True))

    listener.start_listening()
    hotkeys["ctrl+alt+k"]()

    assert received == [True]


def test_hotkey_listener_stop_suppresses_events(monkeypatch, bus):
    config = {"activation_hotkey": "ctrl+k", "clip_hotkey": "ctrl+alt+k"}
    hotkeys = _patch_keyboard(monkeypatch)

    listener = HotkeyListener(config, event_bus=bus)
    received = []
    bus.on("hotkey_pressed", lambda: received.append(True))

    listener.start_listening()
    listener.stop()
    hotkeys["ctrl+k"]()

    assert received == []


def test_hotkey_thread_is_daemon(monkeypatch, bus):
    config = {"activation_hotkey": "ctrl+k", "clip_hotkey": "ctrl+alt+k"}
    _patch_keyboard(monkeypatch)

    thread = HotkeyThread(config, event_bus=bus)
    assert thread.daemon is True


def test_hotkey_thread_stop_unblocks(monkeypatch, bus):
    config = {"activation_hotkey": "ctrl+k", "clip_hotkey": "ctrl+alt+k"}
    _patch_keyboard(monkeypatch)

    thread = HotkeyThread(config, event_bus=bus)
    thread.start()
    thread.stop()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
