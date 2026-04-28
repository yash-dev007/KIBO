"""
tests/test_ai_client.py — Unit tests for AIClient with provider abstraction.

Mocks the LLMProvider so neither Groq nor Ollama is needed at test time.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication

from src.ai.llm_providers.base import ChatChunk, ToolCall


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


CONFIG = {
    "llm_provider": "auto",
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "llama3.2:3b",
    "system_prompt": "You are KIBO.",
    "conversation_history_limit": 5,
    "memory_extraction_inline": True,
}


class FakeProvider:
    """In-memory LLMProvider that yields a configurable chunk sequence."""

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
        for c in self._chunks:
            yield c


def _make_client(qt_app, chunks: list[ChatChunk]):
    """Build an AIClient whose provider returns the given chunk sequence."""
    from src.ai.ai_client import AIClient

    provider = FakeProvider(chunks)
    with patch("src.ai.ai_client.get_provider", return_value=provider):
        client = AIClient(CONFIG)
    return client, provider


# ── Conversation history ────────────────────────────────────────────────


class TestConversationHistory:
    def test_history_trimmed_to_limit(self, qt_app):
        client, _ = _make_client(qt_app, [ChatChunk(done=True)])
        for i in range(12):
            client._history.append({"role": "user", "content": f"u{i}"})
            client._history.append({"role": "assistant", "content": f"a{i}"})
        client._trim_history()
        assert len(client._history) <= CONFIG["conversation_history_limit"] * 2

    def test_clear_history(self, qt_app):
        client, _ = _make_client(qt_app, [ChatChunk(done=True)])
        client._history = [{"role": "user", "content": "hi"}]
        client.clear_history()
        assert client._history == []


# ── Streaming behavior ──────────────────────────────────────────────────


class TestStreaming:
    def test_chunks_emitted_in_order(self, qt_app):
        client, _ = _make_client(
            qt_app,
            [
                ChatChunk(text_delta="Hello"),
                ChatChunk(text_delta=" world"),
                ChatChunk(done=True),
            ],
        )
        chunks: list[str] = []
        full: list[str] = []
        client.response_chunk.connect(chunks.append)
        client.response_done.connect(full.append)

        client.send_query("hi")

        assert chunks == ["Hello", " world"]
        assert full == ["Hello world"]

    def test_history_records_assistant_reply(self, qt_app):
        client, _ = _make_client(
            qt_app,
            [ChatChunk(text_delta="Reply"), ChatChunk(done=True)],
        )
        client.send_query("question")
        assert client._history[-2] == {"role": "user", "content": "question"}
        assert client._history[-1] == {"role": "assistant", "content": "Reply"}


# ── Inline memory tool calls ────────────────────────────────────────────


class TestInlineMemory:
    def test_remember_tool_call_emits_fact(self, qt_app):
        memory_args = {
            "content": "User likes espresso",
            "category": "preference",
            "keywords": ["coffee", "espresso"],
        }
        client, _ = _make_client(
            qt_app,
            [
                ChatChunk(text_delta="Got it!"),
                ChatChunk(tool_call=ToolCall("remember", memory_args)),
                ChatChunk(done=True),
            ],
        )
        captured: list[dict] = []
        client.memory_fact_extracted.connect(captured.append)

        client.send_query("I love espresso")
        assert captured == [memory_args]

    def test_invalid_remember_call_ignored(self, qt_app):
        client, _ = _make_client(
            qt_app,
            [
                ChatChunk(tool_call=ToolCall("remember", {"content": ""})),
                ChatChunk(done=True),
            ],
        )
        captured: list[dict] = []
        client.memory_fact_extracted.connect(captured.append)
        client.send_query("noise")
        assert captured == []

    def test_tools_passed_when_inline_memory_on(self, qt_app):
        client, provider = _make_client(qt_app, [ChatChunk(done=True)])
        client.send_query("remember that I love espresso")
        assert provider.last_tools is not None
        assert provider.last_tools[0]["function"]["name"] == "remember"

    def test_tools_not_passed_for_plain_greeting(self, qt_app):
        client, provider = _make_client(qt_app, [ChatChunk(text_delta="Hi!"), ChatChunk(done=True)])
        client.send_query("hi")
        assert provider.last_tools is None

    def test_hallucinated_memory_json_is_not_streamed_to_chat(self, qt_app):
        memory_json = (
            '{"name": "remember", "parameters": {'
            '"category": "preference", '
            '"content": "User likes espresso.", '
            '"keywords": ["espresso"]'
            "}}"
        )
        client, _ = _make_client(
            qt_app,
            [
                ChatChunk(text_delta=memory_json[:20]),
                ChatChunk(text_delta=memory_json[20:]),
                ChatChunk(done=True),
            ],
        )
        chunks: list[str] = []
        full: list[str] = []
        captured: list[dict] = []
        client.response_chunk.connect(chunks.append)
        client.response_done.connect(full.append)
        client.memory_fact_extracted.connect(captured.append)

        client.send_query("remember that I like espresso")

        assert captured == [{
            "category": "preference",
            "content": "User likes espresso.",
            "keywords": ["espresso"],
        }]
        assert all('"name": "remember"' not in chunk for chunk in chunks)
        assert full == ["Got it! I've saved that to my memory."]

    def test_low_value_hallucinated_memory_json_gets_fallback_reply(self, qt_app):
        memory_json = (
            '{"name": "remember", "parameters": {'
            '"category": "person", "content": "Hello", "keywords": ["greeting"]'
            "}}"
        )
        client, _ = _make_client(
            qt_app,
            [ChatChunk(text_delta=memory_json), ChatChunk(done=True)],
        )
        chunks: list[str] = []
        full: list[str] = []
        captured: list[dict] = []
        client.response_chunk.connect(chunks.append)
        client.response_done.connect(full.append)
        client.memory_fact_extracted.connect(captured.append)

        client.send_query("hi")

        assert captured == []
        assert chunks == ["Hi! How can I help?"]
        assert full == ["Hi! How can I help?"]


# ── Cancellation ────────────────────────────────────────────────────────


class TestCancellation:
    def test_cancel_rolls_back_user_turn(self, qt_app):
        # First chunk text, then we cancel mid-stream.
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
            client = AIClient(CONFIG)
        provider.client = client

        client.send_query("first")
        # User turn must be rolled back; history empty.
        assert client._history == []
