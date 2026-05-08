"""
tts_manager.py — Provider-agnostic TTS on a dedicated daemon Thread.

Picks the best backend (Piper neural > pyttsx3 SAPI5) via
src.ai.tts_providers. Exposes both a one-shot `speak()` method and a
streaming `speak_chunk()` method for sentence-by-sentence playback that
overlaps with token generation.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

from src.ai.tts_providers import TTSProvider, get_provider

logger = logging.getLogger(__name__)


class TTSManager:
    """Plays speech via a configured TTSProvider."""

    def __init__(self, config: dict, event_bus=None) -> None:
        self._config = config
        self._event_bus = event_bus
        self._enabled = config.get("tts_enabled", True)
        self._silent_mode = False
        self._provider: Optional[TTSProvider] = None
        self._chunk_queue: queue.Queue[Optional[str]] = queue.Queue()
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
            if self._event_bus:
                self._event_bus.emit("error_occurred", f"TTS unavailable: {exc}")
            self._enabled = False
            return False

    def speak(self, text: str) -> None:
        if not self._enabled or self._silent_mode or not text.strip():
            if self._event_bus:
                self._event_bus.emit("speech_done")
            return
        if not self._ensure_provider():
            if self._event_bus:
                self._event_bus.emit("speech_done")
            return

        try:
            self._provider.speak(text)
        except Exception as exc:
            logger.error("TTS speak error: %s", exc)
            if self._event_bus:
                self._event_bus.emit("error_occurred", f"TTS error: {exc}")
        finally:
            if self._event_bus:
                self._event_bus.emit("speech_done")

    def speak_chunk(self, sentence: str) -> None:
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

    def end_stream(self) -> None:
        with self._streaming_lock:
            if self._streaming_thread is not None and self._streaming_thread.is_alive():
                self._chunk_queue.put(None)  # sentinel
            else:
                if self._event_bus:
                    self._event_bus.emit("speech_done")

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
            if self._event_bus:
                self._event_bus.emit("speech_done")

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_silent_mode(self, silent: bool) -> None:
        self._silent_mode = silent
        if silent and self._provider is not None:
            try:
                self._provider.stop()
            except Exception:
                pass


class TTSThread(threading.Thread):
    """Daemon thread that owns a TTSManager and dispatches calls via a queue."""

    def __init__(self, config: dict, event_bus=None) -> None:
        super().__init__(daemon=True)
        self._manager = TTSManager(config, event_bus=event_bus)
        self._queue: queue.Queue[Optional[tuple]] = queue.Queue()
        self._stop_event = threading.Event()

    @property
    def manager(self) -> TTSManager:
        return self._manager

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.1)
                try:
                    if item is None:
                        break
                    method, arg = item
                    if arg is None:
                        getattr(self._manager, method)()
                    else:
                        getattr(self._manager, method)(arg)
                finally:
                    self._queue.task_done()
            except queue.Empty:
                continue

    def speak(self, text: str) -> None:
        self._queue.put(("speak", text))

    def speak_chunk(self, sentence: str) -> None:
        self._queue.put(("speak_chunk", sentence))

    def end_stream(self) -> None:
        self._queue.put(("end_stream", None))

    def stop(self) -> None:
        self._stop_event.set()
