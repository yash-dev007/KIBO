"""
tests/test_tts_manager.py — Unit tests for TTSManager.

Uses MockTTSProvider so no audio hardware or real TTS engine is needed.
"""

from __future__ import annotations

import sys
import time
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "tts_enabled": True,
    "tts_provider": "mock",
}


class _FakeTTSProvider:
    """Minimal TTSProvider that records calls without producing audio."""

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.stopped: bool = False

    def is_available(self) -> bool:
        return True

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def stop(self) -> None:
        self.stopped = True


class _BlockingTTSProvider:
    """Blocks during speak() until stop() is called, so interruption is deterministic."""

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.stopped: bool = False
        self.started = threading.Event()
        self.released = threading.Event()

    def is_available(self) -> bool:
        return True

    def speak(self, text: str) -> None:
        self.spoken.append(text)
        self.started.set()
        self.released.wait(timeout=2.0)

    def stop(self) -> None:
        self.stopped = True
        self.released.set()


def _make_manager(config: dict | None = None, provider=None):
    from src.ai.tts_manager import TTSManager
    cfg = config or BASE_CONFIG
    prov = provider or _FakeTTSProvider()

    # Patch get_provider to prevent real provider init, then inject directly.
    # We use a permanent patch on the instance to avoid context-manager timing issues.
    with patch("src.ai.tts_manager.get_provider", return_value=prov):
        mgr = TTSManager(cfg)
        mgr._ensure_provider()  # call while patch is still active
    return mgr, prov


# ---------------------------------------------------------------------------
# TestSpeak — one-shot blocking speak
# ---------------------------------------------------------------------------


class TestSpeak:
    def test_speak_calls_provider(self, qt_app):
        mgr, prov = _make_manager()
        mgr.speak("Hello world")
        assert prov.spoken == ["Hello world"]

    def test_speak_emits_speech_done(self, qt_app):
        mgr, _ = _make_manager()
        done: list[bool] = []
        mgr.speech_done.connect(lambda: done.append(True))
        mgr.speak("Hi")
        assert done == [True]

    def test_speak_noop_when_disabled(self, qt_app):
        mgr, prov = _make_manager({"tts_enabled": False, "tts_provider": "mock"})
        done: list[bool] = []
        mgr.speech_done.connect(lambda: done.append(True))
        mgr.speak("Hello")
        assert prov.spoken == []
        assert done == [True]  # speech_done still fires so Brain returns to IDLE

    def test_speak_noop_in_silent_mode(self, qt_app):
        mgr, prov = _make_manager()
        mgr.set_silent_mode(True)
        done: list[bool] = []
        mgr.speech_done.connect(lambda: done.append(True))
        mgr.speak("Hello")
        assert prov.spoken == []
        assert done == [True]

    def test_speak_noop_on_empty_string(self, qt_app):
        mgr, prov = _make_manager()
        done: list[bool] = []
        mgr.speech_done.connect(lambda: done.append(True))
        mgr.speak("   ")
        assert prov.spoken == []
        assert done == [True]

    def test_speak_error_still_emits_speech_done(self, qt_app):
        """Even if the provider raises, speech_done must fire (Brain must return to IDLE)."""
        mgr, prov = _make_manager()

        def _boom(text):
            raise RuntimeError("boom")

        prov.speak = _boom
        errors: list[str] = []
        done: list[bool] = []
        mgr.error_occurred.connect(errors.append)
        mgr.speech_done.connect(lambda: done.append(True))
        mgr.speak("This will fail")
        assert done == [True]


# ---------------------------------------------------------------------------
# TestStreamingChunks — speak_chunk / end_stream
# ---------------------------------------------------------------------------


class TestStreamingChunks:
    def _drain(self, mgr) -> None:
        """Wait until the streaming thread finishes (or timeout)."""
        deadline = time.time() + 2.0
        while mgr._streaming_thread and mgr._streaming_thread.is_alive():
            time.sleep(0.02)
            if time.time() > deadline:
                raise TimeoutError("Drain thread did not finish in time")

    def test_speak_chunk_drains_in_order(self, qt_app):
        mgr, prov = _make_manager()
        for sentence in ["Hello.", "How are you?", "Fine."]:
            mgr.speak_chunk(sentence)
        mgr.end_stream()
        self._drain(mgr)
        assert prov.spoken == ["Hello.", "How are you?", "Fine."]

    def test_end_stream_sentinel_causes_speech_done(self, qt_app):
        mgr, _ = _make_manager()
        done_event = threading.Event()
        # DirectConnection: fire immediately on the emitting thread (drain thread),
        # without requiring a running Qt event loop.
        mgr.speech_done.connect(lambda: done_event.set(), Qt.DirectConnection)
        mgr.speak_chunk("One sentence.")
        mgr.end_stream()
        self._drain(mgr)
        assert done_event.wait(timeout=2.0), "speech_done not emitted after drain"

    def test_end_stream_with_no_active_thread_emits_immediately(self, qt_app):
        """end_stream with no in-flight drain thread should emit speech_done directly."""
        mgr, _ = _make_manager()
        done: list[bool] = []
        mgr.speech_done.connect(lambda: done.append(True))
        # No speak_chunk called — thread never started
        mgr.end_stream()
        assert done == [True]

    def test_silent_mode_skips_chunk_in_drain(self, qt_app):
        """set_silent_mode mid-drain: drain finishes gracefully and speech_done fires."""
        mgr, prov = _make_manager()
        done_event = threading.Event()
        mgr.speech_done.connect(lambda: done_event.set(), Qt.DirectConnection)
        mgr.speak_chunk("Sentence one.")
        mgr.set_silent_mode(True)
        mgr.end_stream()
        self._drain(mgr)
        assert done_event.wait(timeout=2.0), "speech_done not emitted"

    def test_silent_mode_before_chunk_no_thread_started(self, qt_app):
        """If silent mode is on before any speak_chunk, no thread is started."""
        mgr, prov = _make_manager()
        mgr.set_silent_mode(True)
        mgr.speak_chunk("Should be discarded.")
        assert mgr._streaming_thread is None
        assert prov.spoken == []

    def test_multiple_chunks_all_spoken(self, qt_app):
        mgr, prov = _make_manager()
        chunks = [f"Sentence {i}." for i in range(5)]
        for c in chunks:
            mgr.speak_chunk(c)
        mgr.end_stream()
        self._drain(mgr)
        assert prov.spoken == chunks

    def test_empty_chunk_is_skipped(self, qt_app):
        mgr, prov = _make_manager()
        mgr.speak_chunk("  ")   # whitespace-only
        mgr.speak_chunk("Real sentence.")
        mgr.end_stream()
        self._drain(mgr)
        assert prov.spoken == ["Real sentence."]

    def test_interrupt_stops_current_audio_and_discards_queued_chunks(self, qt_app):
        prov = _BlockingTTSProvider()
        mgr, _ = _make_manager(provider=prov)

        mgr.speak_chunk("Current sentence.")
        assert prov.started.wait(timeout=2.0), "TTS did not start speaking"
        mgr.speak_chunk("Stale queued sentence.")

        mgr.interrupt()
        self._drain(mgr)

        assert prov.stopped is True
        assert prov.spoken == ["Current sentence."]

    def test_new_chunk_after_interrupt_starts_fresh_stream(self, qt_app):
        prov = _BlockingTTSProvider()
        mgr, _ = _make_manager(provider=prov)

        mgr.speak_chunk("Old sentence.")
        assert prov.started.wait(timeout=2.0), "TTS did not start speaking"
        mgr.speak_chunk("Old queued sentence.")
        mgr.interrupt()
        self._drain(mgr)

        prov.started.clear()
        prov.released.clear()
        mgr.set_silent_mode(False)
        mgr.speak_chunk("Fresh sentence.")
        assert prov.started.wait(timeout=2.0), "fresh stream did not start"
        mgr.end_stream()
        prov.released.set()
        self._drain(mgr)

        assert prov.spoken == ["Old sentence.", "Fresh sentence."]


# ---------------------------------------------------------------------------
# TestProviderFailure
# ---------------------------------------------------------------------------


class TestProviderFailure:
    def test_provider_init_failure_emits_error_and_disables(self, qt_app):
        from src.ai.tts_manager import TTSManager
        errors: list[str] = []

        with patch("src.ai.tts_manager.get_provider", side_effect=RuntimeError("no piper")):
            mgr = TTSManager(BASE_CONFIG)
            mgr.error_occurred.connect(errors.append)  # connect BEFORE _ensure_provider
            mgr._ensure_provider()   # triggers the error path while patch is active

        assert len(errors) == 1
        assert mgr._enabled is False

    def test_speak_chunk_without_provider_is_noop(self, qt_app):
        from src.ai.tts_manager import TTSManager
        with patch("src.ai.tts_manager.get_provider", side_effect=RuntimeError("no provider")):
            mgr = TTSManager(BASE_CONFIG)
        mgr._enabled = False   # short-circuit

        # Should not raise
        mgr.speak_chunk("Won't be spoken")
        # No thread started
        assert mgr._streaming_thread is None
