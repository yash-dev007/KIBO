"""
sentence_buffer.py — Splits a token stream into speakable sentences.
"""
from __future__ import annotations

import re
import threading
from typing import Iterator

# A sentence ends at . ! ? followed by space/end, or at a newline.
_SENTENCE_END = re.compile(r"([\.\!\?…]+)(\s|$)|\n+")


class SentenceBuffer:
    """Accumulates text deltas; emits each completed sentence via EventBus."""

    def __init__(self, *, min_chars: int = 12, event_bus=None) -> None:
        self._event_bus = event_bus
        self._buf = ""
        self._min_chars = min_chars
        self._lock = threading.Lock()

    def push(self, delta: str) -> None:
        if not delta:
            return
        with self._lock:
            self._buf += delta
            sentences = list(self._extract_sentences())
        for sentence in sentences:
            if self._event_bus:
                self._event_bus.emit("sentence_ready", sentence)

    def flush(self) -> None:
        with self._lock:
            leftover = self._buf.strip()
            self._buf = ""
        if leftover and self._event_bus:
            self._event_bus.emit("sentence_ready", leftover)
        if self._event_bus:
            self._event_bus.emit("flushed")

    def reset(self) -> None:
        with self._lock:
            self._buf = ""

    def _extract_sentences(self) -> Iterator[str]:
        while True:
            match = _SENTENCE_END.search(self._buf)
            if not match:
                return
            cut = match.end()
            while True:
                candidate = self._buf[:cut].strip()
                if len(candidate) >= self._min_chars:
                    break
                next_match = _SENTENCE_END.search(self._buf, cut)
                if not next_match:
                    return
                cut = next_match.end()
            self._buf = self._buf[cut:]
            yield candidate
