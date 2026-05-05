"""
sentence_buffer.py — Splits a token stream into speakable sentences.

Used to bridge the LLM streaming output into the TTS provider so that
audio playback starts after the *first* complete sentence rather than
waiting for the full reply. Cuts perceived latency dramatically.
"""

from __future__ import annotations

import re
from typing import Iterator, Optional

from PySide6.QtCore import QObject, Signal, Slot

# A sentence ends at . ! ? followed by space/end, or at a newline.
# We also flush on em-dash + space to keep the cadence natural for TTS.
_SENTENCE_END = re.compile(r"([\.\!\?…]+)(\s|$)|\n+")


class SentenceBuffer(QObject):
    """Accumulates text deltas; emits each completed sentence."""

    sentence_ready = Signal(str)
    flushed = Signal()

    def __init__(
        self, parent: Optional[QObject] = None, *, min_chars: int = 12
    ) -> None:
        super().__init__(parent)
        self._buf = ""
        self._min_chars = min_chars

    @Slot(str)
    def push(self, delta: str) -> None:
        """Append a new token delta and emit any completed sentences."""
        if not delta:
            return
        self._buf += delta
        for sentence in self._extract_sentences():
            self.sentence_ready.emit(sentence)

    @Slot()
    def flush(self) -> None:
        """End-of-stream: emit whatever remains, then clear."""
        leftover = self._buf.strip()
        if leftover:
            self.sentence_ready.emit(leftover)
        self._buf = ""
        self.flushed.emit()

    @Slot()
    def reset(self) -> None:
        """Discard buffered text without emitting anything.

        Call this at the start of every new conversation turn to prevent
        leftover fragments from a cancelled or interrupted stream from
        leaking into the next reply.
        """
        self._buf = ""

    def _extract_sentences(self) -> Iterator[str]:
        """Pull as many full sentences out of the buffer as possible.

        Avoids speaking absurdly short fragments alone ("OK.") by extending
        across the next terminator until min_chars is satisfied.
        """
        while True:
            match = _SENTENCE_END.search(self._buf)
            if not match:
                return
            cut = match.end()

            # Extend across short fragments until we have enough characters
            # or run out of terminators in the buffer.
            while True:
                candidate = self._buf[:cut].strip()
                if len(candidate) >= self._min_chars:
                    break
                next_match = _SENTENCE_END.search(self._buf, cut)
                if not next_match:
                    return  # wait for more text
                cut = next_match.end()

            self._buf = self._buf[cut:]
            yield candidate
