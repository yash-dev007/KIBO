"""
hotkey_listener.py — Global hotkey listener (default: Ctrl+K).

Runs the keyboard library's blocking wait loop on a QThread so it never
blocks the Qt event loop. Emits hotkey_pressed signal on the main thread
via Qt's cross-thread signal mechanism.
"""

from __future__ import annotations

import logging
from typing import Optional

import keyboard
from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


class HotkeyListener(QObject):
    """Lives on a QThread. Emits hotkey_pressed when the hotkey fires."""

    hotkey_pressed = Signal()

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._hotkey = config.get("activation_hotkey", "ctrl+k")
        self._running = False

    def start_listening(self) -> None:
        """Called once the worker thread starts."""
        self._running = True
        logger.info("HotkeyListener: registering hotkey '%s'.", self._hotkey)
        try:
            keyboard.add_hotkey(self._hotkey, self._on_hotkey)
        except Exception as exc:
            logger.error("HotkeyListener error: %s", exc)

    def stop(self) -> None:
        self._running = False
        try:
            keyboard.unhook_all()
        except Exception:
            pass

    def _on_hotkey(self) -> None:
        if self._running:
            logger.debug("Hotkey '%s' pressed.", self._hotkey)
            self.hotkey_pressed.emit()


class HotkeyThread(QThread):
    """Convenience wrapper: owns HotkeyListener and runs it on this thread."""

    hotkey_pressed = Signal()

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._listener = HotkeyListener(config)
        self._listener.moveToThread(self)
        self._listener.hotkey_pressed.connect(self.hotkey_pressed)

    def run(self) -> None:
        self._listener.start_listening()
        self.exec()

    def stop(self) -> None:
        self._listener.stop()
        self.quit()
        self.wait(2000)
