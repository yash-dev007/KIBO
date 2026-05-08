"""
hotkey_listener.py — Global hotkey listener (default: Ctrl+K).

Runs the keyboard library's blocking wait on a daemon Thread so it never
blocks the main thread. Emits EventBus events when registered hotkeys fire.
"""

from __future__ import annotations

import logging
import threading

import keyboard

logger = logging.getLogger(__name__)


class HotkeyListener:
    """Registers global hotkeys and emits EventBus events when they fire."""

    def __init__(self, config: dict, event_bus=None) -> None:
        self._hotkey = config.get("activation_hotkey", "ctrl+k")
        self._clip_hotkey = config.get("clip_hotkey", "ctrl+alt+k")
        self._event_bus = event_bus
        self._running = False

    def start_listening(self) -> None:
        self._running = True
        logger.info(
            "HotkeyListener: registering '%s' (talk) and '%s' (clip).",
            self._hotkey,
            self._clip_hotkey,
        )
        try:
            keyboard.add_hotkey(self._hotkey, self._on_hotkey)
            keyboard.add_hotkey(self._clip_hotkey, self._on_clip_hotkey)
        except Exception as exc:
            logger.error("HotkeyListener error: %s", exc)

    def stop(self) -> None:
        self._running = False
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    def _on_hotkey(self) -> None:
        if self._running and self._event_bus:
            logger.debug("Hotkey '%s' pressed.", self._hotkey)
            self._event_bus.emit("hotkey_pressed")

    def _on_clip_hotkey(self) -> None:
        if self._running and self._event_bus:
            logger.debug("Clip hotkey '%s' pressed.", self._clip_hotkey)
            self._event_bus.emit("clip_hotkey_pressed")


class HotkeyThread(threading.Thread):
    """Daemon thread that owns a HotkeyListener and keeps it running."""

    def __init__(self, config: dict, event_bus=None) -> None:
        super().__init__(daemon=True)
        self._listener = HotkeyListener(config, event_bus=event_bus)
        self._stop_event = threading.Event()

    def run(self) -> None:
        self._listener.start_listening()
        self._stop_event.wait()

    def stop(self) -> None:
        self._listener.stop()
        self._stop_event.set()
