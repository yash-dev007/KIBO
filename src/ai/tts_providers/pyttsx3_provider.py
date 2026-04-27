"""SAPI5 TTS via pyttsx3 — fallback when Piper isn't available."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class Pyttsx3Provider:
    def __init__(self, config: dict) -> None:
        self._config = config
        self._engine = None
        self._rate = int(config.get("tts_rate", 175))

    def is_available(self) -> bool:
        return self._init_engine()

    def _init_engine(self) -> bool:
        if self._engine is not None:
            return True
        try:
            try:
                import pythoncom

                pythoncom.CoInitialize()
            except ImportError:
                pass
            import pyttsx3

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self._rate)
            return True
        except Exception as exc:
            logger.error("pyttsx3 init failed: %s", exc)
            return False

    def speak(self, text: str) -> None:
        if not self._init_engine():
            return
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as exc:
            logger.error("pyttsx3 speak error: %s", exc)

    def stop(self) -> None:
        if self._engine is None:
            return
        try:
            self._engine.stop()
        except Exception:
            pass
