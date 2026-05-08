"""
tests/test_ai_client.py — Unit tests for AIClient with provider abstraction.

Mocks the LLMProvider so neither Groq nor Ollama is needed at test time.
"""

from __future__ import annotations

from typing import Iterator
from unittest.mock import patch

import pytest

from src.api.event_bus import EventBus
from src.ai.llm_providers.base import ChatChunk, ToolCall


@pytest.fixture
def bus():
    return EventBus()


CONFIG = {
    "llm_provider": "auto",
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "llama3.2:3b",
    "system_prompt": "You are KIBO.",
    "conversation_history_limit": 5,
    "memory_extraction_inline": True,
}


class FakeProvider:
    def __init__(self, chunks: list[ChatChunk]) -> None:
        self._chunks = chunks
        self.last_messages: list[dict] = []
        self.last_system: str = ""
        self.last_tools = None

    def is_available(self) -> bool:
        return True

    def stream_chat(self, system, messages, tools=None) -> Iterator[ChatChunk]:
        self.last_system = system
        self.last_messages = list(messages)
        self.last_tools = tools
        yield from self._chunks


def _make_client(bus, chunks: list[ChatChunk]):
    from src.ai.ai_client import AIClient

    provider = FakeProvider(chunks)
    with patch("src.ai.ai_client.get_provider", return_value=provider):
        client = AIClient(CONFIG, event_bus=bus)
    return client, provider


# ── Conversation history ────────────────────────────────────────────────


class TestConversationHistory:
    def test_history_trimmed_to_limit(self, bus):
        client, _ = _make_client(bus, [ChatChunk(done=True)])
        for i in range(12):
            client._history.append({"role": "user", "content": f"u{i}"})
            client._history.append({"role": "assistant", "content": f"a{i}"})
        client._trim_history()
        assert len(client._history) <= CONFIG["conversation_history_limit"] * 2

    def test_clear_history(self, bus):
        client, _ = _make_client(bus, [ChatChunk(done=True)])
        client._history = [{"role": "user", "content": "hi"}]
        client.clear_history()
        assert client._history == []


# ── Streaming behavior ──────────────────────────────────────────────────


class TestStreaming:
    def test_chunks_emitted_in_order(self, bus):
        client, _ = _make_client(bus, [
            ChatChunk(text_delta="Hello"),
            ChatChunk(text_delta=" world"),
            ChatChunk(done=True),
        ])
        chunks: list[str] = []
        full: list[str] = []
        bus.on("response_chunk", chunks.append)
        bus.on("response_done", full.append)

        client.send_query("hi")

        assert chunks == ["Hello", " world"]
        assert full == ["Hello world"]

    def test_history_records_assistant_reply(self, bus):
        client, _ = _make_client(bus, [
            ChatChunk(text_delta="Reply"),
            ChatChunk(done=True),
        ])
        client.send_query("question")
        assert client._history[-2] == {"role": "user", "content": "question"}
        assert client._history[-1] == {"role": "assistant", "content": "Reply"}


# ── Inline memory tool calls ────────────────────────────────────────────


class TestInlineMemory:
    def test_remember_tool_call_emits_fact(self, bus):
        memory_args = {
            "content": "User likes espresso",
            "category": "preference",
            "keywords": ["coffee", "espresso"],
        }
        client, _ = _make_client(bus, [
            ChatChunk(text_delta="Got it!"),
            ChatChunk(tool_call=ToolCall("remember", memory_args)),
            ChatChunk(done=True),
        ])
        captured: list[dict] = []
        bus.on("memory_fact_extracted", captured.append)

        client.send_query("I love espresso")
        assert captured == [memory_args]

    def test_invalid_remember_call_ignored(self, bus):
        client, _ = _make_client(bus, [
            ChatChunk(tool_call=ToolCall("remember", {"content": ""})),
            ChatChunk(done=True),
        ])
        captured: list[dict] = []
        bus.on("memory_fact_extracted", captured.append)
        client.send_query("noise")
        assert captured == []

    def test_tools_passed_when_inline_memory_on(self, bus):
        client, provider = _make_client(bus, [ChatChunk(done=True)])
        client.send_query("remember that I love espresso")
        assert provider.last_tools is not None
        assert provider.last_tools[0]["function"]["name"] == "remember"

    def test_tools_not_passed_for_plain_greeting(self, bus):
        client, provider = _make_client(bus, [
            ChatChunk(text_delta="Hi!"),
            ChatChunk(done=True),
        ])
        client.send_query("hi")
        assert provider.last_tools is None

    def test_hallucinated_memory_json_is_not_streamed_to_chat(self, bus):
        memory_json = (
            '{"name": "remember", "parameters": {'
            '"category": "preference", '
            '"content": "User likes espresso.", '
            '"keywords": ["espresso"]'
            "}}"
        )
        client, _ = _make_client(bus, [
            ChatChunk(text_delta=memory_json[:20]),
            ChatChunk(text_delta=memory_json[20:]),
            ChatChunk(done=True),
        ])
        chunks: list[str] = []
        full: list[str] = []
        captured: list[dict] = []
        bus.on("response_chunk", chunks.append)
        bus.on("response_done", full.append)
        bus.on("memory_fact_extracted", captured.append)

        client.send_query("remember that I like espresso")

        assert captured == [{
            "category": "preference",
            "content": "User likes espresso.",
            "keywords": ["espresso"],
        }]
        assert all('"name": "remember"' not in chunk for chunk in chunks)
        assert full == ["Got it! I've saved that to my memory."]

    def test_low_value_hallucinated_memory_json_gets_fallback_reply(self, bus):
        memory_json = (
            '{"name": "remember", "parameters": {'
            '"category": "person", "content": "Hello", "keywords": ["greeting"]'
            "}}"
        )
        client, _ = _make_client(bus, [
            ChatChunk(text_delta=memory_json),
            ChatChunk(done=True),
        ])
        chunks: list[str] = []
        full: list[str] = []
        captured: list[dict] = []
        bus.on("response_chunk", chunks.append)
        bus.on("response_done", full.append)
        bus.on("memory_fact_extracted", captured.append)

        client.send_query("hi")

        assert captured == []
        assert chunks == ["Hi! How can I help?"]
        assert full == ["Hi! How can I help?"]


# ── Cancellation ────────────────────────────────────────────────────────


class TestCancellation:
    def test_cancel_rolls_back_user_turn(self, bus):
        class CancelOnSecond:
            def __init__(self) -> None:
                self.client = None

            def is_available(self) -> bool:
                return True

            def stream_chat(self, system, messages, tools=None):
                yield ChatChunk(text_delta="part")
                self.client.cancel_current()
                yield ChatChunk(text_delta="never")
                yield ChatChunk(done=True)

        from src.ai.ai_client import AIClient

        provider = CancelOnSecond()
        with patch("src.ai.ai_client.get_provider", return_value=provider):
            client = AIClient(CONFIG, event_bus=bus)
        provider.client = client

        client.send_query("first")
        assert client._history == []


# ── AIThread ────────────────────────────────────────────────────────────


class TestAIThread:
    def test_ai_thread_is_daemon(self, bus):
        from src.ai.ai_client import AIThread
        with patch("src.ai.ai_client.get_provider", return_value=FakeProvider([])):
            thread = AIThread(CONFIG, event_bus=bus)
        assert thread.daemon is True

    def test_ai_thread_dispatches_send_query(self, bus):
        from src.ai.ai_client import AIThread
        provider = FakeProvider([ChatChunk(text_delta="hello"), ChatChunk(done=True)])
        with patch("src.ai.ai_client.get_provider", return_value=provider):
            thread = AIThread(CONFIG, event_bus=bus)

        full: list[str] = []
        bus.on("response_done", full.append)

        thread.start()
        thread.send_query("test")
        thread._queue.join()
        thread.stop()
        thread.join(timeout=2.0)

        assert full == ["hello"]

    def test_ai_thread_stop_exits_cleanly(self, bus):
        from src.ai.ai_client import AIThread
        with patch("src.ai.ai_client.get_provider", return_value=FakeProvider([])):
            thread = AIThread(CONFIG, event_bus=bus)
        thread.start()
        thread.stop()
        thread.join(timeout=2.0)
        assert not thread.is_alive()
