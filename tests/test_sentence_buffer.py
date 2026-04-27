"""tests/test_sentence_buffer.py — Unit tests for the streaming sentence splitter."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


def _drive(buf, parts: list[str]) -> list[str]:
    out: list[str] = []
    buf.sentence_ready.connect(out.append)
    for p in parts:
        buf.push(p)
    return out


class TestSentenceSplitting:
    def test_single_sentence_emits_at_terminator(self, qt_app):
        from src.ai.sentence_buffer import SentenceBuffer

        buf = SentenceBuffer()
        out = _drive(buf, ["Hello world", "."])
        # Period at end-of-buffer is enough; we emit eagerly so TTS starts ASAP.
        assert out == ["Hello world."]

    def test_two_sentences_streamed(self, qt_app):
        from src.ai.sentence_buffer import SentenceBuffer

        buf = SentenceBuffer()
        out: list[str] = []
        buf.sentence_ready.connect(out.append)
        for delta in ["Hello there. ", "How are you?", " Fine."]:
            buf.push(delta)
        buf.flush()
        # Expect: "Hello there.", "How are you?", "Fine."
        assert "Hello there." in out
        assert "How are you?" in out
        # Tail flushed:
        assert out[-1] == "Fine."

    def test_short_fragment_not_emitted_alone(self, qt_app):
        from src.ai.sentence_buffer import SentenceBuffer

        buf = SentenceBuffer(min_chars=12)
        out: list[str] = []
        buf.sentence_ready.connect(out.append)
        # "OK." is below min_chars and should be merged with the next sentence.
        buf.push("OK. ")
        assert out == []
        buf.push("Then we proceed.")
        buf.push(" ")
        # Should merge into one piece
        assert any("Then we proceed" in s for s in out)

    def test_flush_emits_remainder_then_flushed_signal(self, qt_app):
        from src.ai.sentence_buffer import SentenceBuffer

        buf = SentenceBuffer()
        out: list[str] = []
        flushed = []
        buf.sentence_ready.connect(out.append)
        buf.flushed.connect(lambda: flushed.append(True))

        buf.push("incomplete sentence with no terminator")
        assert out == []  # nothing emitted yet
        buf.flush()
        assert out == ["incomplete sentence with no terminator"]
        assert flushed == [True]

    def test_newline_acts_as_sentence_break(self, qt_app):
        from src.ai.sentence_buffer import SentenceBuffer

        buf = SentenceBuffer()
        out: list[str] = []
        buf.sentence_ready.connect(out.append)
        buf.push("First line that is long enough\nSecond line follows here")
        buf.flush()
        assert len(out) == 2
        assert out[0].startswith("First line")
        assert out[1].startswith("Second line")

    def test_empty_push_is_noop(self, qt_app):
        from src.ai.sentence_buffer import SentenceBuffer

        buf = SentenceBuffer()
        out: list[str] = []
        buf.sentence_ready.connect(out.append)
        buf.push("")
        buf.flush()
        assert out == []
