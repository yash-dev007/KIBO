"""
tts_manager.py — Provider-agnostic TTS on a dedicated QThread.

Picks the best backend (Piper neural > pyttsx3 SAPI5) via
src.ai.tts_providers. Exposes both a one-shot `speak()` slot and a
streaming `speak_chunk()` slot for sentence-by-sentence playback that
overlaps with token generation.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

from PySide6.QtCore import QMetaObject, QObject, QThread, Qt, Signal, Slot, Q_ARG

from src.ai.tts_providers import TTSProvider, get_provider

logger = logging.getLogger(__name__)


class TTSManager(QObject):
    """Plays speech via a configured TTSProvider. Lives on a QThread."""

    speech_done = Signal()
    error_occurred = Signal(str)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._enabled = config.get("tts_enabled", True)
        self._silent_mode = False
        self._provider: Optional[TTSProvider] = None
        self._chunk_queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._streaming_thread: Optional[threading.Thread] = None
        self._streaming_lock = threading.Lock()

    def _ensure_provider(self) -> bool:
        if self._provider is not None:
            return True
        if not self._enabled:
            return False
        try:
            self._provider = get_provider(self._config)
            return True
        except Exception as exc:
            logger.error("TTS provider init failed: %s", exc)
            self.error_occurred.emit(f"TTS unavailable: {exc}")
            self._enabled = False
            return False

    @Slot(str)
    def speak(self, text: str) -> None:
        """One-shot blocking speak (used for full-reply mode)."""
        if not self._enabled or self._silent_mode or not text.strip():
            self.speech_done.emit()
            return
        if not self._ensure_provider():
            self.speech_done.emit()
            return

        try:
            self._provider.speak(text)
        except Exception as exc:
            logger.error("TTS speak error: %s", exc)
            self.error_occurred.emit(f"TTS error: {exc}")
        finally:
            self.speech_done.emit()

    # ── Streaming sentence-by-sentence ──────────────────────────────────

    @Slot(str)
    def speak_chunk(self, sentence: str) -> None:
        """Queue a sentence for playback. Spawns the drain thread on first call."""
        if not self._enabled or self._silent_mode or not sentence.strip():
            return
        if not self._ensure_provider():
            return

        with self._streaming_lock:
            self._chunk_queue.put(sentence)
            if self._streaming_thread is None or not self._streaming_thread.is_alive():
                self._streaming_thread = threading.Thread(
                    target=self._drain_chunks, daemon=True
                )
                self._streaming_thread.start()

    @Slot()
    def end_stream(self) -> None:
        """Signal end of stream — drain thread will emit speech_done after last chunk."""
        with self._streaming_lock:
            if self._streaming_thread is not None and self._streaming_thread.is_alive():
                self._chunk_queue.put(None)  # sentinel
            else:
                self.speech_done.emit()

    def _drain_chunks(self) -> None:
        try:
            while True:
                chunk = self._chunk_queue.get()
                if chunk is None:
                    break
                if self._silent_mode:
                    continue
                try:
                    self._provider.speak(chunk)
                except Exception as exc:
                    logger.error("TTS chunk error: %s", exc)
        finally:
            self.speech_done.emit()

    # ── Mode toggles ────────────────────────────────────────────────────

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    @Slot(bool)
    def set_silent_mode(self, silent: bool) -> None:
        self._silent_mode = silent
        if silent and self._provider is not None:
            try:
                self._provider.stop()
            except Exception:
                pass


class TTSThread(QThread):
    """Owns TTSManager on this thread."""

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
            self._manager, "speak", Qt.QueuedConnection, Q_ARG(str, text)
        )

    def speak_chunk(self, sentence: str) -> None:
        QMetaObject.invokeMethod(
            self._manager, "speak_chunk", Qt.QueuedConnection, Q_ARG(str, sentence)
        )

    def end_stream(self) -> None:
        QMetaObject.invokeMethod(self._manager, "end_stream", Qt.QueuedConnection)

    def stop(self) -> None:
        self.quit()
        self.wait(3000)

    @property
    def manager(self) -> TTSManager:
        return self._manager
