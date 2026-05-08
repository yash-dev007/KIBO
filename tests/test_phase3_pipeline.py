"""
tests/test_phase3_pipeline.py — End-to-end Phase 3 pipeline integration tests.

Wires AIClient (MockLLM) → SentenceBuffer → TTSManager (MockTTS) without
any network, Ollama, audio hardware, or Qt threads.

Verifies the three Phase 3 success criteria:
1. TTS receives sentences, not one giant blob (streaming works).
2. Buffer is clean between turns (no cross-turn leakage).
3. Cancel mid-stream does not leak text to TTS.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.llm_providers.base import ChatChunk, ToolCall
from src.api.event_bus import EventBus


# ---------------------------------------------------------------------------
# Fake providers
# ---------------------------------------------------------------------------


class FakeLLMProvider:
    """Streams configurable ChatChunk sequences with no network."""

    def __init__(self, chunks: list[ChatChunk]) -> None:
        self._chunks = chunks
        self.call_count = 0

    def is_available(self) -> bool:
        return True

    def stream_chat(self, system, messages, tools=None) -> Iterator[ChatChunk]:
        self.call_count += 1
        yield from self._chunks


class FakeTTSProvider:
    """Captures speak() calls without audio output."""

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.first_speak_time: float | None = None

    def is_available(self) -> bool:
        return True

    def speak(self, text: str) -> None:
        if self.first_speak_time is None:
            self.first_speak_time = time.perf_counter()
        self.spoken.append(text)

    def stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONFIG = {
    "llm_provider": "mock",
    "system_prompt": "You are KIBO.",
    "conversation_history_limit": 5,
    "memory_extraction_inline": False,  # keep tests simple
    "tts_enabled": True,
    "tts_provider": "mock",
}


def _build_pipeline(chunks: list[ChatChunk]):
    """
    Build the wired pipeline:
      AIClient → SentenceBuffer → TTSManager
    Returns (client, sentence_buffer, tts_manager, fake_tts_provider, bus).
    All run synchronously on the calling thread — no QThreads.
    """
    from src.ai.ai_client import AIClient
    from src.ai.sentence_buffer import SentenceBuffer
    from src.ai.tts_manager import TTSManager

    bus = EventBus()
    llm = FakeLLMProvider(chunks)
    tts_prov = FakeTTSProvider()

    with patch("src.ai.ai_client.get_provider", return_value=llm):
        client = AIClient(CONFIG, event_bus=bus)

    with patch("src.ai.tts_manager.get_provider", return_value=tts_prov):
        tts = TTSManager(CONFIG)
        tts._ensure_provider()  # must be inside patch context

    buf = SentenceBuffer(event_bus=bus)

    # Wire: AIClient → SentenceBuffer → TTSManager via EventBus
    bus.on("response_chunk", buf.push)
    bus.on("sentence_ready", tts.speak_chunk)
    bus.on("flushed", tts.end_stream)

    return client, buf, tts, tts_prov, bus


def _drain(tts) -> None:
    """Block until the streaming drain thread finishes."""
    deadline = time.time() + 3.0
    while tts._streaming_thread and tts._streaming_thread.is_alive():
        time.sleep(0.02)
        if time.time() > deadline:
            raise TimeoutError("TTS drain thread did not finish")


# ---------------------------------------------------------------------------
# TestConversationPipeline
# ---------------------------------------------------------------------------


class TestConversationPipeline:

    def test_text_query_produces_speech_chunks(self):
        """AIClient → SentenceBuffer → TTS: TTS.speak() must be called at least once."""
        chunks = [
            ChatChunk(text_delta="Hello there. "),
            ChatChunk(text_delta="How are you doing today?"),
            ChatChunk(done=True),
        ]
        client, buf, tts, prov, bus = _build_pipeline(chunks)

        full: list[str] = []
        bus.on("response_done", full.append)
        client.send_query("hi")
        buf.flush()
        _drain(tts)

        assert len(prov.spoken) >= 1
        assert full == ["Hello there. How are you doing today?"]

    def test_tts_receives_sentences_not_full_blob(self):
        """
        The streaming pipeline must split on sentence boundaries.
        A reply with two clear sentences must produce at least two TTS calls.
        """
        chunks = [
            ChatChunk(text_delta="First sentence here. "),
            ChatChunk(text_delta="Second sentence follows."),
            ChatChunk(done=True),
        ]
        client, buf, tts, prov, bus = _build_pipeline(chunks)
        client.send_query("go")
        buf.flush()
        _drain(tts)

        # SentenceBuffer should have split on the period — at least 2 speak() calls
        assert len(prov.spoken) >= 2, (
            f"Expected >= 2 TTS chunks (sentence-level streaming), got: {prov.spoken}"
        )

    def test_buffer_reset_prevents_cross_turn_leakage(self):
        """
        After a reset(), a new turn must not inherit leftovers from the previous turn.
        Simulate a partial first turn (no terminator) then reset before second turn.
        """
        from src.ai.sentence_buffer import SentenceBuffer

        bus = EventBus()
        buf = SentenceBuffer(event_bus=bus)
        emitted: list[str] = []
        bus.on("sentence_ready", emitted.append)

        # First turn — partial fragment with no sentence terminator
        buf.push("This is an unfinished thought")

        # Reset before new turn (the fix we're implementing)
        buf.reset()

        # Second turn — clean start
        buf.push("Clean start for second turn.")
        buf.flush()

        # Only the second turn's text should appear
        assert len(emitted) == 1
        assert "Clean start" in emitted[0]
        assert "unfinished thought" not in emitted[0]

    def test_cancel_mid_stream_does_not_leak_to_tts(self):
        """Cancelling the AIClient mid-stream must not push extra text into TTS."""
        from src.ai.ai_client import AIClient
        from src.ai.sentence_buffer import SentenceBuffer
        from src.ai.tts_manager import TTSManager

        bus = EventBus()
        tts_prov = FakeTTSProvider()

        class CancelAfterFirst:
            def __init__(self, client_ref):
                self.client = client_ref
                self.count = 0

            def is_available(self):
                return True

            def stream_chat(self, system, messages, tools=None):
                yield ChatChunk(text_delta="First chunk. ")
                self.client.cancel_current()
                yield ChatChunk(text_delta="Should not appear.")
                yield ChatChunk(done=True)

        llm = CancelAfterFirst(None)
        with patch("src.ai.ai_client.get_provider", return_value=llm):
            client = AIClient(CONFIG, event_bus=bus)
        llm.client = client

        with patch("src.ai.tts_manager.get_provider", return_value=tts_prov):
            tts = TTSManager(CONFIG)
            tts._ensure_provider()  # inside patch context

        buf = SentenceBuffer(event_bus=bus)
        bus.on("response_chunk", buf.push)
        bus.on("sentence_ready", tts.speak_chunk)
        bus.on("flushed", tts.end_stream)

        client.send_query("trigger")
        # After cancel, history should be rolled back
        assert client._history == []
        # "Should not appear." must not reach TTS
        for text in tts_prov.spoken:
            assert "Should not appear" not in text

    def test_memory_fact_extracted_during_conversation(self):
        """A `remember` tool call in the stream must fire memory_fact_extracted."""
        memory_args = {
            "content": "User drinks espresso",
            "category": "preference",
            "keywords": ["coffee", "espresso"],
        }
        chunks = [
            ChatChunk(text_delta="Got it! "),
            ChatChunk(tool_call=ToolCall("remember", memory_args)),
            ChatChunk(done=True),
        ]
        client, buf, tts, _, bus = _build_pipeline(chunks)
        facts: list[dict] = []
        bus.on("memory_fact_extracted", facts.append)

        client.send_query("I love espresso")

        assert facts == [memory_args]

    def test_response_done_fires_after_full_reply(self):
        """response_done must carry the complete assembled text."""
        chunks = [
            ChatChunk(text_delta="Hello "),
            ChatChunk(text_delta="world!"),
            ChatChunk(done=True),
        ]
        client, buf, tts, _, bus = _build_pipeline(chunks)
        done_texts: list[str] = []
        bus.on("response_done", done_texts.append)

        client.send_query("hi")

        assert done_texts == ["Hello world!"]
