"""
tests/test_voice_listener.py — Unit tests for VoiceListener.

All tests run without hardware (sounddevice mocked) and without the
faster-whisper model (WhisperModel mocked).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CONFIG = {
    "stt_model": "base.en",
    "stt_use_vad": False,          # default to RMS so VAD isn't loaded
    "stt_vad_provider": "rms",
    "stt_vad_threshold": 0.5,
    "stt_min_silence_ms": 600,
    "recording_max_seconds": 8,
}


def _make_listener(config: dict | None = None):
    from src.ai.voice_listener import VoiceListener
    return VoiceListener(config or BASE_CONFIG)


def _silent_frame(n: int = 512) -> np.ndarray:
    """Near-zero amplitude — below RMS threshold."""
    return np.zeros(n, dtype=np.float32)


def _speech_frame(n: int = 512, amplitude: float = 0.05) -> np.ndarray:
    """Sine-wave audio at human-speech amplitude."""
    t = np.linspace(0, 1, n)
    return (np.sin(2 * np.pi * 440 * t) * amplitude).astype(np.float32)


# ---------------------------------------------------------------------------
# TestFrameSpeechDetection — pure logic, no hardware
# ---------------------------------------------------------------------------


class TestFrameSpeechDetection:
    def test_explicit_rms_provider_does_not_load_silero(self, qt_app):
        listener = _make_listener({**BASE_CONFIG, "stt_vad_provider": "rms", "stt_use_vad": True})
        assert listener._vad_provider == "rms"
        assert listener._use_vad is False
        assert listener._load_vad() is False

    def test_explicit_off_provider_disables_silero(self, qt_app):
        listener = _make_listener({**BASE_CONFIG, "stt_vad_provider": "off", "stt_use_vad": True})
        assert listener._vad_provider == "off"
        assert listener._use_vad is False

    def test_legacy_true_maps_to_silero_when_no_provider_key(self, qt_app):
        cfg = dict(BASE_CONFIG)
        cfg.pop("stt_vad_provider", None)
        cfg["stt_use_vad"] = True
        listener = _make_listener(cfg)
        assert listener._vad_provider == "silero_local"
        assert listener._use_vad is True

    def test_rms_below_threshold_is_not_speech(self, qt_app):
        listener = _make_listener()
        frame = _silent_frame()
        assert listener._frame_is_speech(frame) is False

    def test_rms_above_threshold_is_speech(self, qt_app):
        listener = _make_listener()
        frame = _speech_frame(amplitude=0.05)
        assert listener._frame_is_speech(frame) is True

    def test_rms_boundary_at_threshold(self, qt_app):
        """Frames above the 0.01 RMS threshold are treated as speech."""
        listener = _make_listener()
        # Use 0.011 to stay safely above the float32 precision boundary.
        frame = np.full(512, 0.011, dtype=np.float32)
        assert listener._frame_is_speech(frame) is True

    def test_rms_exactly_below_threshold_is_not_speech(self, qt_app):
        """Frames below 0.01 RMS are silent."""
        listener = _make_listener()
        frame = np.full(512, 0.005, dtype=np.float32)
        assert listener._frame_is_speech(frame) is False

    def test_vad_disabled_uses_rms(self, qt_app):
        """When stt_use_vad is False, _vad is None and RMS path is taken."""
        cfg = {**BASE_CONFIG, "stt_use_vad": False}
        listener = _make_listener(cfg)
        assert listener._vad is None
        frame = _speech_frame()
        assert listener._frame_is_speech(frame) is True

    def test_vad_error_falls_back_to_rms(self, qt_app):
        """If VAD model raises an exception, _vad is set to None and RMS is used."""
        listener = _make_listener()

        # Simulate a loaded VAD that then fails
        bad_vad = MagicMock()
        bad_vad.side_effect = RuntimeError("VAD crashed")
        listener._vad = bad_vad

        frame = _speech_frame()
        # Should not raise — falls back to RMS
        result = listener._frame_is_speech(frame)
        assert result is True          # RMS path gives True for this frame
        assert listener._vad is None   # VAD disabled for the rest of the session



# ---------------------------------------------------------------------------
# TestTranscription — mocked WhisperModel
# ---------------------------------------------------------------------------


class TestTranscription:
    def _make_with_whisper(self, segments_text: list[str]):
        """Return a listener whose Whisper model yields given segment texts."""
        listener = _make_listener()

        segments = [MagicMock(text=t) for t in segments_text]
        mock_whisper = MagicMock()
        mock_whisper.transcribe.return_value = (segments, MagicMock())
        listener._whisper = mock_whisper
        return listener

    def test_transcript_emitted_when_speech_found(self, qt_app):
        listener = self._make_with_whisper([" Hello", " world"])
        received: list[str] = []
        listener.transcript_ready.connect(received.append)

        audio = _speech_frame(n=16000)
        listener._transcribe(audio)

        assert received == ["Hello world"]

    def test_error_emitted_when_transcript_empty(self, qt_app):
        listener = self._make_with_whisper([""])
        errors: list[str] = []
        no_speech: list[bool] = []
        listener.error_occurred.connect(errors.append)
        listener.no_speech_detected.connect(lambda: no_speech.append(True))

        listener._transcribe(_speech_frame(n=16000))

        assert len(errors) == 1
        assert no_speech == [True]
        assert "No speech detected" in errors[0]

    def test_error_emitted_when_all_segments_whitespace(self, qt_app):
        listener = self._make_with_whisper(["   ", "\t"])
        errors: list[str] = []
        listener.error_occurred.connect(errors.append)
        listener._transcribe(_speech_frame())
        assert errors

    def test_transcription_exception_emits_error(self, qt_app):
        listener = _make_listener()
        mock_whisper = MagicMock()
        mock_whisper.transcribe.side_effect = RuntimeError("model exploded")
        listener._whisper = mock_whisper

        errors: list[str] = []
        listener.error_occurred.connect(errors.append)

        listener._transcribe(_speech_frame(n=16000))

        assert len(errors) == 1
        assert "Transcription failed" in errors[0]

    def test_whisper_load_failure_emits_error(self, qt_app):
        """_load_whisper fails gracefully when WhisperModel raises."""
        listener = _make_listener()
        errors: list[str] = []
        listener.error_occurred.connect(errors.append)

        listener._whisper = None  # ensure it tries to load
        with patch("faster_whisper.WhisperModel", side_effect=RuntimeError("no model files")):
            result = listener._load_whisper()

        assert result is False
        assert len(errors) == 1

    def test_whisper_loaded_once_on_repeated_calls(self, qt_app):
        """_load_whisper returns True immediately if model already loaded."""
        listener = _make_listener()
        listener._whisper = MagicMock()  # pre-load

        with patch("faster_whisper.WhisperModel") as mock_cls:
            result = listener._load_whisper()

        mock_cls.assert_not_called()
        assert result is True

    def test_warm_up_loads_whisper_without_recording(self, qt_app):
        listener = _make_listener()
        with patch.object(listener, "_load_whisper", return_value=True) as load_whisper:
            listener.warm_up()
        load_whisper.assert_called_once()
        assert listener._is_recording is False


# ---------------------------------------------------------------------------
# TestHotkeySlot — concurrent-access guard
# ---------------------------------------------------------------------------


class TestHotkeySlot:
    def test_second_hotkey_ignored_while_recording(self, qt_app):
        """If _is_recording is already True, on_hotkey_pressed is a no-op."""
        listener = _make_listener()
        listener._is_recording = True

        calls: list[bool] = []
        listener.recording_started.connect(lambda: calls.append(True))

        listener.on_hotkey_pressed()

        assert calls == []  # recording_started never fired

    def test_recording_flag_cleared_after_load_failure(self, qt_app):
        """If Whisper fails to load, _is_recording is reset to False."""
        listener = _make_listener()
        errors: list[str] = []
        listener.error_occurred.connect(errors.append)

        with patch.object(listener, "_load_whisper", return_value=False):
            listener.on_hotkey_pressed()

        assert listener._is_recording is False
