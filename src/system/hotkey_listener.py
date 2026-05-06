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
from PySide6.QtCore import QMetaObject, QObject, QThread, Qt, Signal, Slot, Q_ARG

logger = logging.getLogger(__name__)


class HotkeyListener(QObject):
    """Lives on a QThread. Emits signals when registered hotkeys fire."""

    hotkey_pressed = Signal()
    clip_hotkey_pressed = Signal()
    registration_failed = Signal(str)  # emitted with the failed hotkey string

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._hotkey = config.get("activation_hotkey", "ctrl+k")
        self._clip_hotkey = config.get("clip_hotkey", "ctrl+alt+k")
        self._running = False
        # Track our own registrations so stop() can remove only KIBO's hooks
        # without disturbing other code that may be using the keyboard library.
        self._registered_handles: dict[str, object] = {}

    def is_registered(self, hotkey: str) -> bool:
        """Return True if the given hotkey is currently registered by KIBO."""
        return hotkey in self._registered_handles

    def _register(self, hotkey: str, callback) -> None:
        try:
            handle = keyboard.add_hotkey(hotkey, callback)
        except Exception as exc:
            logger.error("HotkeyListener: failed to register '%s': %s", hotkey, exc)
            self.registration_failed.emit(hotkey)
            return
        self._registered_handles[hotkey] = handle

    def start_listening(self) -> None:
        """Called once the worker thread starts."""
        self._running = True
        logger.info(
            "HotkeyListener: registering '%s' (talk) and '%s' (clip).",
            self._hotkey,
            self._clip_hotkey,
        )
        self._register(self._hotkey, self._on_hotkey)
        self._register(self._clip_hotkey, self._on_clip_hotkey)

    def stop(self) -> None:
        self._running = False
        # Remove only the hooks we registered, leaving any non-KIBO hooks
        # registered elsewhere in the process untouched.
        for hotkey, handle in list(self._registered_handles.items()):
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                # Fall back to removing by hotkey string
                try:
                    keyboard.remove_hotkey(hotkey)
                except Exception:
                    pass
        self._registered_handles.clear()

    def rebind(self, talk_hotkey: str | None = None, clip_hotkey: str | None = None) -> None:
        """Replace one or both hotkeys at runtime.

        Each rebind only touches the affected hook; the other stays live.
        """
        if talk_hotkey and talk_hotkey != self._hotkey:
            self._unregister(self._hotkey)
            self._hotkey = talk_hotkey
            if self._running:
                self._register(self._hotkey, self._on_hotkey)
        if clip_hotkey and clip_hotkey != self._clip_hotkey:
            self._unregister(self._clip_hotkey)
            self._clip_hotkey = clip_hotkey
            if self._running:
                self._register(self._clip_hotkey, self._on_clip_hotkey)

    def _unregister(self, hotkey: str) -> None:
        handle = self._registered_handles.pop(hotkey, None)
        if handle is None:
            return
        try:
            keyboard.remove_hotkey(handle)
        except Exception:
            try:
                keyboard.remove_hotkey(hotkey)
            except Exception:
                pass

    @Slot(str, str)
    def rebind_slot(self, talk_hotkey: str, clip_hotkey: str) -> None:
        self.rebind(talk_hotkey=talk_hotkey, clip_hotkey=clip_hotkey)

    def _on_hotkey(self) -> None:
        if self._running:
            logger.debug("Hotkey '%s' pressed.", self._hotkey)
            self.hotkey_pressed.emit()

    def _on_clip_hotkey(self) -> None:
        if self._running:
            logger.debug("Clip hotkey '%s' pressed.", self._clip_hotkey)
            self.clip_hotkey_pressed.emit()


class HotkeyThread(QThread):
    """Convenience wrapper: owns HotkeyListener and runs it on this thread."""

    hotkey_pressed = Signal()
    clip_hotkey_pressed = Signal()
    registration_failed = Signal(str)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._listener = HotkeyListener(config)
        self._listener.moveToThread(self)
        self._listener.hotkey_pressed.connect(self.hotkey_pressed)
        self._listener.clip_hotkey_pressed.connect(self.clip_hotkey_pressed)
        self._listener.registration_failed.connect(self.registration_failed)

    def run(self) -> None:
        self._listener.start_listening()
        self.exec()

    def stop(self) -> None:
        self._listener.stop()
        self.quit()
        self.wait(2000)

    def rebind(self, talk_hotkey: str, clip_hotkey: str) -> None:
        QMetaObject.invokeMethod(
            self._listener,
            "rebind_slot",
            Qt.QueuedConnection,
            Q_ARG(str, talk_hotkey),
            Q_ARG(str, clip_hotkey),
        )
