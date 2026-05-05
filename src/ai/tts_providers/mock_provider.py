"""
src/ai/tts_providers/mock_provider.py — Silent TTS provider for tests.

Usage in config.json:  "tts_provider": "mock"

Records all speak() calls in ``spoken`` without producing any audio.
Useful for:
  - Unit/integration tests (no audio hardware required)
  - CI pipelines
  - Latency profiling without playback blocking
"""

from __future__ import annotations

import time


class MockTTSProvider:
    """Silent TTS provider that records speak() calls.

    Attributes:
        spoken: Ordered list of texts passed to speak().
        first_speak_time: perf_counter() timestamp of the first speak() call,
                          or None if speak() hasn't been called yet. Use this
                          to measure TTFS in tests.
    """

    def __init__(self, config: dict | None = None) -> None:  # noqa: ARG002
        self.spoken: list[str] = []
        self.first_speak_time: float | None = None
        self._stopped: bool = False

    def is_available(self) -> bool:
        return True

    def speak(self, text: str) -> None:
        """Record the text; does not produce audio."""
        if self.first_speak_time is None:
            self.first_speak_time = time.perf_counter()
        self.spoken.append(text)

    def stop(self) -> None:
        """Mark playback stopped."""
        self._stopped = True

    def reset(self) -> None:
        """Clear recorded state between test cases."""
        self.spoken.clear()
        self.first_speak_time = None
        self._stopped = False
