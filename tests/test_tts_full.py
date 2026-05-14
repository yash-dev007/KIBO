"""
tests/test_tts_full.py — Comprehensive TTS test suite.

Coverage:
  - MockTTSProvider: speak, stop, reset, timing, edge cases
  - get_provider(): mock / piper-missing / piper-no-model / pyttsx3 fallback
  - TTSManager: speak, speak_chunk, end_stream, silent mode, disabled,
                provider init failure, error during speak, concurrent chunks
  - TTSThread: dispatch, stop, concurrent safety
  - Integration: sentence_buffer → tts_thread pipeline (E2E)
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.ai.tts_providers.mock_provider import MockTTSProvider
from src.ai.tts_manager import TTSManager, TTSThread
from src.api.event_bus import EventBus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def mock_provider():
    return MockTTSProvider()


@pytest.fixture
def enabled_config():
    return {"tts_enabled": True, "tts_provider": "mock"}


@pytest.fixture
def disabled_config():
    return {"tts_enabled": False, "tts_provider": "mock"}


def _manager_with_mock(config, bus) -> tuple[TTSManager, MockTTSProvider]:
    """Return a TTSManager pre-wired with a MockTTSProvider."""
    mgr = TTSManager(config, event_bus=bus)
    provider = MockTTSProvider()
    mgr._provider = provider
    mgr._enabled = config.get("tts_enabled", True)
    return mgr, provider


# ══════════════════════════════════════════════════════════════════════════════
# MockTTSProvider
# ══════════════════════════════════════════════════════════════════════════════

class TestMockTTSProvider:
    def test_is_available(self, mock_provider):
        assert mock_provider.is_available() is True

    def test_speak_records_text(self, mock_provider):
        mock_provider.speak("hello world")
        assert mock_provider.spoken == ["hello world"]

    def test_speak_multiple_accumulates(self, mock_provider):
        mock_provider.speak("one")
        mock_provider.speak("two")
        mock_provider.speak("three")
        assert mock_provider.spoken == ["one", "two", "three"]

    def test_first_speak_time_set_on_first_call(self, mock_provider):
        assert mock_provider.first_speak_time is None
        mock_provider.speak("hi")
        assert mock_provider.first_speak_time is not None

    def test_first_speak_time_not_updated_on_subsequent_calls(self, mock_provider):
        mock_provider.speak("first")
        t1 = mock_provider.first_speak_time
        mock_provider.speak("second")
        assert mock_provider.first_speak_time == t1

    def test_stop_sets_stopped_flag(self, mock_provider):
        mock_provider.stop()
        assert mock_provider._stopped is True

    def test_reset_clears_state(self, mock_provider):
        mock_provider.speak("something")
        mock_provider.stop()
        mock_provider.reset()
        assert mock_provider.spoken == []
        assert mock_provider.first_speak_time is None
        assert mock_provider._stopped is False

    def test_speak_empty_string(self, mock_provider):
        mock_provider.speak("")
        assert mock_provider.spoken == [""]

    def test_speak_whitespace_only(self, mock_provider):
        mock_provider.speak("   ")
        assert mock_provider.spoken == ["   "]

    def test_speak_unicode(self, mock_provider):
        mock_provider.speak("こんにちは 🐊")
        assert mock_provider.spoken == ["こんにちは 🐊"]

    def test_speak_very_long_text(self, mock_provider):
        text = "word " * 1000
        mock_provider.speak(text)
        assert mock_provider.spoken == [text]


# ══════════════════════════════════════════════════════════════════════════════
# get_provider() — provider selection logic
# ══════════════════════════════════════════════════════════════════════════════

class TestGetProvider:
    def test_mock_choice_returns_mock(self):
        from src.ai.tts_providers import get_provider
        provider = get_provider({"tts_provider": "mock"})
        assert isinstance(provider, MockTTSProvider)

    def test_piper_missing_sdk_falls_back_to_pyttsx3(self):
        from src.ai.tts_providers import get_provider
        with patch.dict("sys.modules", {"piper": None, "piper.voice": None}):
            with patch("src.ai.tts_providers.pyttsx3_provider.Pyttsx3Provider") as MockP:
                MockP.return_value = MagicMock()
                provider = get_provider({"tts_provider": "auto"})
                assert provider is MockP.return_value

    def test_piper_missing_model_falls_back_to_pyttsx3(self, tmp_path):
        from src.ai.tts_providers import get_provider
        config = {
            "tts_provider": "auto",
            "piper_model": "en_US-amy-medium",
            "piper_models_dir": str(tmp_path),  # empty dir — no .onnx files
        }
        # piper-tts SDK may or may not be installed; either way, model is absent
        with patch("src.ai.tts_providers.pyttsx3_provider.Pyttsx3Provider") as MockP:
            MockP.return_value = MagicMock()
            provider = get_provider(config)
            assert provider is MockP.return_value

    def test_explicit_piper_raises_when_unavailable(self, tmp_path):
        from src.ai.tts_providers import get_provider
        config = {
            "tts_provider": "piper",
            "piper_model": "en_US-amy-medium",
            "piper_models_dir": str(tmp_path),
        }
        with pytest.raises(RuntimeError, match="Piper requested but unavailable"):
            get_provider(config)

    def test_mock_is_silent(self):
        from src.ai.tts_providers import get_provider
        provider = get_provider({"tts_provider": "mock"})
        provider.speak("test")  # must not raise or produce audio
        assert provider.spoken == ["test"]  # type: ignore[attr-defined]


# ══════════════════════════════════════════════════════════════════════════════
# TTSManager — speak()
# ══════════════════════════════════════════════════════════════════════════════

class TestTTSManagerSpeak:
    def test_speak_calls_provider_and_emits_done(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        mgr.speak("hello")

        assert provider.spoken == ["hello"]
        assert done == [True]

    def test_speak_empty_skips_provider_but_emits_done(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        mgr.speak("")

        assert provider.spoken == []
        assert done == [True]

    def test_speak_whitespace_only_skips_provider(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        mgr.speak("   \t\n  ")

        assert provider.spoken == []
        assert done == [True]

    def test_speak_when_disabled_skips_provider(self, bus, disabled_config):
        mgr = TTSManager(disabled_config, event_bus=bus)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        mgr.speak("ignored")

        assert done == [True]

    def test_speak_in_silent_mode_skips_provider(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        mgr.set_silent_mode(True)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        mgr.speak("silent")

        assert provider.spoken == []
        assert done == [True]

    def test_speak_provider_exception_emits_error(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        provider.speak = MagicMock(side_effect=RuntimeError("audio device missing"))
        errors = []
        done = []
        bus.on("error_occurred", errors.append)
        bus.on("speech_done", lambda: done.append(True))

        mgr.speak("boom")

        assert any("TTS error" in e for e in errors)
        assert done == [True]  # speech_done always emitted

    def test_speak_provider_init_failure_emits_done(self, bus, enabled_config):
        mgr = TTSManager(enabled_config, event_bus=bus)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        with patch.object(mgr, "_ensure_provider", return_value=False):
            mgr.speak("no provider")

        assert done == [True]

    def test_speak_multiline_text(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        mgr.speak("line one\nline two\nline three")
        assert provider.spoken == ["line one\nline two\nline three"]

    def test_speak_unicode(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        mgr.speak("Héllo wörld 🌍")
        assert provider.spoken == ["Héllo wörld 🌍"]

    def test_speak_without_event_bus_does_not_crash(self, enabled_config):
        mgr = TTSManager(enabled_config, event_bus=None)
        mgr._provider = MockTTSProvider()
        mgr.speak("no bus")  # must not raise


# ══════════════════════════════════════════════════════════════════════════════
# TTSManager — speak_chunk() / end_stream()
# ══════════════════════════════════════════════════════════════════════════════

class TestTTSManagerStream:
    def _drain(self, mgr: TTSManager, timeout: float = 3.0) -> None:
        if mgr._streaming_thread:
            mgr._streaming_thread.join(timeout=timeout)

    def test_single_chunk_then_end(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        mgr.speak_chunk("sentence one")
        mgr.end_stream()
        self._drain(mgr)

        assert provider.spoken == ["sentence one"]
        assert done == [True]

    def test_multiple_chunks_in_order(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        for sentence in ["alpha", "beta", "gamma"]:
            mgr.speak_chunk(sentence)
        mgr.end_stream()
        self._drain(mgr)

        assert provider.spoken == ["alpha", "beta", "gamma"]
        assert done == [True]

    def test_end_stream_with_no_chunks_emits_done(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        mgr.end_stream()

        assert done == [True]
        assert provider.spoken == []

    def test_chunks_skipped_in_silent_mode(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        mgr.set_silent_mode(True)

        mgr.speak_chunk("should be skipped")
        mgr.end_stream()
        self._drain(mgr)

        assert provider.spoken == []

    def test_chunks_skipped_when_disabled(self, bus, disabled_config):
        mgr, provider = _manager_with_mock(disabled_config, bus)
        mgr._enabled = False

        mgr.speak_chunk("ignored")
        mgr.end_stream()

        assert provider.spoken == []

    def test_chunk_provider_error_continues_drain(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        call_count = []
        provider.speak = MagicMock(side_effect=lambda t: call_count.append(t) or (_ for _ in ()).throw(RuntimeError("fail")) if len(call_count) == 1 else None)

        mgr.speak_chunk("first")
        mgr.speak_chunk("second")
        mgr.end_stream()
        self._drain(mgr)
        # Stream completes; no exception leaks out

    def test_empty_chunk_skipped(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        mgr.speak_chunk("")
        mgr.end_stream()

        assert provider.spoken == []

    def test_whitespace_chunk_skipped(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)

        mgr.speak_chunk("   ")
        mgr.end_stream()
        self._drain(mgr)

        assert provider.spoken == []

    def test_second_stream_after_first_completes(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)

        mgr.speak_chunk("stream one")
        mgr.end_stream()
        self._drain(mgr)

        provider.reset()

        mgr.speak_chunk("stream two")
        mgr.end_stream()
        self._drain(mgr)

        assert provider.spoken == ["stream two"]


# ══════════════════════════════════════════════════════════════════════════════
# TTSManager — silent mode / set_enabled
# ══════════════════════════════════════════════════════════════════════════════

class TestTTSManagerModes:
    def test_set_silent_mode_true_calls_provider_stop(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        provider.stop = MagicMock()

        mgr.set_silent_mode(True)

        assert mgr._silent_mode is True
        provider.stop.assert_called_once()

    def test_set_silent_mode_false_does_not_stop(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        provider.stop = MagicMock()
        mgr._silent_mode = True

        mgr.set_silent_mode(False)

        assert mgr._silent_mode is False
        provider.stop.assert_not_called()

    def test_set_silent_mode_without_provider_does_not_crash(self, bus, enabled_config):
        mgr = TTSManager(enabled_config, event_bus=bus)
        mgr._provider = None
        mgr.set_silent_mode(True)  # must not raise

    def test_set_enabled_false_prevents_speak(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)
        mgr.set_enabled(False)
        done = []
        bus.on("speech_done", lambda: done.append(True))

        mgr.speak("silenced")

        assert provider.spoken == []
        assert done == [True]

    def test_set_enabled_true_restores_speak(self, bus, disabled_config):
        mgr, provider = _manager_with_mock(disabled_config, bus)
        mgr.set_enabled(True)

        mgr.speak("restored")

        assert provider.spoken == ["restored"]


# ══════════════════════════════════════════════════════════════════════════════
# TTSThread
# ══════════════════════════════════════════════════════════════════════════════

class TestTTSThread:
    def test_is_daemon(self, bus, enabled_config):
        thread = TTSThread(enabled_config, event_bus=bus)
        assert thread.daemon is True

    def test_speak_dispatches_to_manager(self, bus, enabled_config):
        thread = TTSThread(enabled_config, event_bus=bus)
        calls = []
        thread._manager.speak = lambda t: calls.append(t)

        thread.start()
        thread.speak("dispatched")
        thread._queue.join()
        thread.stop()
        thread.join(timeout=2.0)

        assert calls == ["dispatched"]

    def test_speak_chunk_dispatches(self, bus, enabled_config):
        thread = TTSThread(enabled_config, event_bus=bus)
        calls = []
        thread._manager.speak_chunk = lambda t: calls.append(t)

        thread.start()
        thread.speak_chunk("chunk")
        thread._queue.join()
        thread.stop()
        thread.join(timeout=2.0)

        assert calls == ["chunk"]

    def test_end_stream_dispatches(self, bus, enabled_config):
        thread = TTSThread(enabled_config, event_bus=bus)
        called = []
        thread._manager.end_stream = lambda: called.append(True)

        thread.start()
        thread.end_stream()
        thread._queue.join()
        thread.stop()
        thread.join(timeout=2.0)

        assert called == [True]

    def test_stop_exits_cleanly(self, bus, enabled_config):
        thread = TTSThread(enabled_config, event_bus=bus)
        thread.start()
        thread.stop()
        thread.join(timeout=2.0)
        assert not thread.is_alive()

    def test_multiple_speaks_ordered(self, bus, enabled_config):
        thread = TTSThread(enabled_config, event_bus=bus)
        calls = []
        thread._manager.speak = lambda t: calls.append(t)

        thread.start()
        for word in ["one", "two", "three"]:
            thread.speak(word)
        thread._queue.join()
        thread.stop()
        thread.join(timeout=2.0)

        assert calls == ["one", "two", "three"]

    def test_stop_without_start_does_not_crash(self, bus, enabled_config):
        thread = TTSThread(enabled_config, event_bus=bus)
        thread.stop()  # must not raise


# ══════════════════════════════════════════════════════════════════════════════
# End-to-end: SentenceBuffer → TTSThread pipeline
# ══════════════════════════════════════════════════════════════════════════════

class TestE2EPipeline:
    """Full pipeline: token stream → sentence buffer → TTS thread → MockProvider."""

    def _build_pipeline(self, bus):
        from src.ai.sentence_buffer import SentenceBuffer

        config = {"tts_enabled": True, "tts_provider": "mock"}
        tts_thread = TTSThread(config, event_bus=bus)
        provider = MockTTSProvider()
        tts_thread._manager._provider = provider

        buf = SentenceBuffer(event_bus=bus)

        bus.on("sentence_ready", tts_thread.speak_chunk)
        bus.on("flushed", lambda: tts_thread.end_stream())

        tts_thread.start()
        return buf, tts_thread, provider

    def _wait_for_drain(self, tts_thread: TTSThread, timeout: float = 3.0):
        tts_thread._queue.join()
        mgr = tts_thread._manager
        if mgr._streaming_thread and mgr._streaming_thread.is_alive():
            mgr._streaming_thread.join(timeout=timeout)

    def test_single_sentence_spoken(self, bus):
        buf, tts_thread, provider = self._build_pipeline(bus)

        buf.push("Hello, how are you doing today?")
        buf.flush()
        self._wait_for_drain(tts_thread)

        tts_thread.stop()
        tts_thread.join(timeout=2.0)

        assert len(provider.spoken) == 1
        assert "Hello" in provider.spoken[0]

    def test_two_sentences_both_spoken(self, bus):
        buf, tts_thread, provider = self._build_pipeline(bus)

        buf.push("The first sentence is here. The second sentence follows now.")
        buf.flush()
        self._wait_for_drain(tts_thread)

        tts_thread.stop()
        tts_thread.join(timeout=2.0)

        combined = " ".join(provider.spoken)
        assert "first sentence" in combined
        assert "second sentence" in combined

    def test_streamed_tokens_reassembled(self, bus):
        buf, tts_thread, provider = self._build_pipeline(bus)

        tokens = ["The ", "weather ", "is ", "nice ", "today. ", "Go ", "outside!"]
        for token in tokens:
            buf.push(token)
        buf.flush()
        self._wait_for_drain(tts_thread)

        tts_thread.stop()
        tts_thread.join(timeout=2.0)

        combined = " ".join(provider.spoken)
        assert "weather" in combined
        assert "outside" in combined

    def test_empty_response_produces_no_speech(self, bus):
        buf, tts_thread, provider = self._build_pipeline(bus)

        buf.push("")
        buf.flush()
        self._wait_for_drain(tts_thread)

        tts_thread.stop()
        tts_thread.join(timeout=2.0)

        assert provider.spoken == []

    def test_whitespace_only_response_produces_no_speech(self, bus):
        buf, tts_thread, provider = self._build_pipeline(bus)

        buf.push("   \n\t  ")
        buf.flush()
        self._wait_for_drain(tts_thread)

        tts_thread.stop()
        tts_thread.join(timeout=2.0)

        assert provider.spoken == []

    def test_first_token_timing_recorded(self, bus):
        buf, tts_thread, provider = self._build_pipeline(bus)

        buf.push("KIBO is your friendly desktop companion.")
        buf.flush()
        self._wait_for_drain(tts_thread)

        tts_thread.stop()
        tts_thread.join(timeout=2.0)

        assert provider.first_speak_time is not None

    def test_multiple_flushes_accumulate_speech(self, bus):
        from src.ai.sentence_buffer import SentenceBuffer

        config = {"tts_enabled": True, "tts_provider": "mock"}
        tts_thread = TTSThread(config, event_bus=bus)
        provider = MockTTSProvider()
        tts_thread._manager._provider = provider
        tts_thread.start()

        spoken_sentences = []
        bus.on("sentence_ready", spoken_sentences.append)

        buf1 = SentenceBuffer(event_bus=bus)
        bus.on("sentence_ready", tts_thread.speak_chunk)
        bus.on("flushed", lambda: tts_thread.end_stream())

        buf1.push("Response one is complete.")
        buf1.flush()
        tts_thread._queue.join()

        buf2 = SentenceBuffer(event_bus=bus)
        buf2.push("Response two follows shortly.")
        buf2.flush()
        tts_thread._queue.join()

        if tts_thread._manager._streaming_thread:
            tts_thread._manager._streaming_thread.join(timeout=3.0)

        tts_thread.stop()
        tts_thread.join(timeout=2.0)

        assert len(provider.spoken) >= 2

    def test_pipeline_with_tts_disabled_produces_no_speech(self, bus):
        from src.ai.sentence_buffer import SentenceBuffer

        config = {"tts_enabled": False, "tts_provider": "mock"}
        tts_thread = TTSThread(config, event_bus=bus)
        provider = MockTTSProvider()
        tts_thread._manager._provider = provider
        tts_thread._manager._enabled = False

        buf = SentenceBuffer(event_bus=bus)
        bus.on("sentence_ready", tts_thread.speak_chunk)
        bus.on("flushed", lambda: tts_thread.end_stream())

        tts_thread.start()
        buf.push("This should not be spoken.")
        buf.flush()
        tts_thread._queue.join()

        tts_thread.stop()
        tts_thread.join(timeout=2.0)

        assert provider.spoken == []


# ══════════════════════════════════════════════════════════════════════════════
# Edge cases — concurrency
# ══════════════════════════════════════════════════════════════════════════════

class TestConcurrency:
    def test_concurrent_speak_chunks_all_delivered(self, bus, enabled_config):
        mgr, provider = _manager_with_mock(enabled_config, bus)

        chunks = [f"sentence {i}" for i in range(10)]
        threads = [
            threading.Thread(target=mgr.speak_chunk, args=(c,))
            for c in chunks
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        mgr.end_stream()
        if mgr._streaming_thread:
            mgr._streaming_thread.join(timeout=5.0)

        assert len(provider.spoken) == 10
        assert sorted(provider.spoken) == sorted(chunks)

    def test_thread_safe_speak_from_multiple_threads(self, bus, enabled_config):
        thread = TTSThread(enabled_config, event_bus=bus)
        calls = []
        thread._manager.speak = lambda t: calls.append(t)
        thread.start()

        def _speak(text):
            thread.speak(text)

        workers = [threading.Thread(target=_speak, args=(f"msg{i}",)) for i in range(5)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()

        thread._queue.join()
        thread.stop()
        thread.join(timeout=2.0)

        assert len(calls) == 5
