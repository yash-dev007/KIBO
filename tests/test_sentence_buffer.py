"""tests/test_sentence_buffer.py — Unit tests for the streaming sentence splitter."""
from __future__ import annotations

import pytest
from src.api.event_bus import EventBus
from src.ai.sentence_buffer import SentenceBuffer


@pytest.fixture
def bus():
    return EventBus()


def _drive(buf, bus, parts: list[str]) -> list[str]:
    out: list[str] = []
    bus.on("sentence_ready", out.append)
    for p in parts:
        buf.push(p)
    return out


class TestSentenceSplitting:
    def test_single_sentence_emits_at_terminator(self, bus):
        buf = SentenceBuffer(event_bus=bus)
        out = _drive(buf, bus, ["Hello world", "."])
        assert out == ["Hello world."]

    def test_two_sentences_streamed(self, bus):
        buf = SentenceBuffer(event_bus=bus)
        out: list[str] = []
        bus.on("sentence_ready", out.append)
        for delta in ["Hello there. ", "How are you?", " Fine."]:
            buf.push(delta)
        buf.flush()
        assert "Hello there." in out
        assert "How are you?" in out
        assert out[-1] == "Fine."

    def test_short_fragment_not_emitted_alone(self, bus):
        buf = SentenceBuffer(min_chars=12, event_bus=bus)
        out: list[str] = []
        bus.on("sentence_ready", out.append)
        buf.push("OK. ")
        assert out == []
        buf.push("Then we proceed.")
        buf.push(" ")
        assert any("Then we proceed" in s for s in out)

    def test_flush_emits_remainder_then_flushed_signal(self, bus):
        buf = SentenceBuffer(event_bus=bus)
        out: list[str] = []
        flushed = []
        bus.on("sentence_ready", out.append)
        bus.on("flushed", lambda: flushed.append(True))

        buf.push("incomplete sentence with no terminator")
        assert out == []
        buf.flush()
        assert out == ["incomplete sentence with no terminator"]
        assert flushed == [True]

    def test_newline_acts_as_sentence_break(self, bus):
        buf = SentenceBuffer(event_bus=bus)
        out: list[str] = []
        bus.on("sentence_ready", out.append)
        buf.push("First line that is long enough\nSecond line follows here")
        buf.flush()
        assert len(out) == 2
        assert out[0].startswith("First line")
        assert out[1].startswith("Second line")

    def test_empty_push_is_noop(self, bus):
        buf = SentenceBuffer(event_bus=bus)
        out: list[str] = []
        bus.on("sentence_ready", out.append)
        buf.push("")
        buf.flush()
        assert out == []
