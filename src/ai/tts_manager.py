"""
tts_manager.py — Text-to-speech using Windows SAPI5 via pyttsx3.

pyttsx3 has its own internal event loop and MUST run on a dedicated thread.
Emits speech_done when finished speaking.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QMetaObject, QObject, QThread, Qt, Signal, Slot, Q_ARG

logger = logging.getLogger(__name__)


class TTSManager(QObject):
    """
    Wraps pyttsx3 for async speech output.
    Must be moved to a QThread before use.
    """

    speech_done = Signal()
    error_occurred = Signal(str)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._engine = None
        self._enabled = config.get("tts_enabled", True)
        self._silent_mode = False

    def _init_engine(self) -> bool:
        if self._engine is not None:
            return True
        if not self._enabled:
            return False
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except ImportError:
                pass
            import pyttsx3
            self._engine = pyttsx3.init()
            rate = self._config.get("tts_rate", 175)
            self._engine.setProperty("rate", rate)
            logger.info("TTS engine initialized (rate=%d).", rate)
            return True
        except Exception as exc:
            logger.error("TTS init failed: %s", exc)
            self.error_occurred.emit(f"TTS unavailable: {exc}")
            self._enabled = False
            return False

    @Slot(str)
    def speak(self, text: str) -> None:
        """Speak text synchronously (blocks this thread, not the UI thread)."""
        if not self._enabled or self._silent_mode:
            self.speech_done.emit()
            return

        if not self._init_engine():
            self.speech_done.emit()
            return

        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as exc:
            logger.error("TTS speak error: %s", exc)
            self.error_occurred.emit(f"TTS error: {exc}")
        finally:
            self.speech_done.emit()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    @Slot(bool)
    def set_silent_mode(self, silent: bool) -> None:
        self._silent_mode = silent


class TTSThread(QThread):
    """Convenience wrapper: owns TTSManager on this thread."""

    speech_done = Signal()

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._manager = TTSManager(config)
        self._manager.moveToThread(self)
        self._manager.speech_done.connect(self.speech_done)

    def run(self) -> None:
        self.exec()

    def speak(self, text: str) -> None:
        QMetaObject.invokeMethod(
            self._manager, "speak",
            Qt.QueuedConnection,
            Q_ARG(str, text),
        )

    def stop(self) -> None:
        self.quit()
        self.wait(3000)

    @property
    def manager(self) -> TTSManager:
        return self._manager
