"""Protocol for TTS providers."""

from __future__ import annotations

from typing import Protocol


class TTSProvider(Protocol):
    """Common interface every TTS backend must implement."""

    def is_available(self) -> bool: ...

    def speak(self, text: str) -> None:
        """Synthesize and play `text` synchronously. Blocks calling thread
        (caller is expected to be on a worker thread)."""
        ...

    def stop(self) -> None:
        """Best-effort interrupt of any in-flight playback."""
        ...
