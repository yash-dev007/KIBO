"""
src/ai/llm_providers/mock_provider.py — Deterministic LLM provider for tests.

Usage in config.json:  "llm_provider": "mock"

Streams a configurable list of ChatChunk objects with an optional inter-chunk
delay. Useful for:
  - Unit/integration tests (no network required)
  - Demo/offline mode
  - Latency profiling (set delay_ms to simulate a slow model)
"""

from __future__ import annotations

import time
from typing import Iterator

from .base import ChatChunk, LLMProvider, ToolCall


class MockLLMProvider:
    """Deterministic LLM provider that streams pre-defined responses.

    Args:
        responses: List of strings; each string becomes a single text_delta
                   chunk. A final ``ChatChunk(done=True)`` is appended
                   automatically.
        tool_calls: Optional list of ToolCall objects to inject *after* all
                    text chunks but *before* the done sentinel.
        delay_ms:   Milliseconds to sleep between each chunk (default 0).
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        tool_calls: list[ToolCall] | None = None,
        delay_ms: int = 0,
        config: dict | None = None,
    ) -> None:
        if config:
            responses = config.get("demo_llm_responses", responses)
            delay_ms = int(config.get("demo_llm_delay_ms", delay_ms))
        self._responses: list[str] = responses or ["Mock response."]
        self._tool_calls: list[ToolCall] = tool_calls or []
        self._delay: float = delay_ms / 1000.0
        self.call_count: int = 0

    def is_available(self) -> bool:
        return True

    def stream_chat(
        self,
        system: str,  # noqa: ARG002
        messages: list[dict],  # noqa: ARG002
        tools: list[dict] | None = None,  # noqa: ARG002
    ) -> Iterator[ChatChunk]:
        """Yield chunks from *responses* → *tool_calls* → done."""
        self.call_count += 1

        for text in self._responses:
            if self._delay:
                time.sleep(self._delay)
            yield ChatChunk(text_delta=text)

        for tc in self._tool_calls:
            if self._delay:
                time.sleep(self._delay)
            yield ChatChunk(tool_call=tc)

        yield ChatChunk(done=True)
