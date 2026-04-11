"""
voice_listener.py — Record audio after hotkey, transcribe with faster-whisper.

Flow:
  1. on_hotkey_pressed() is called → enters RECORDING state
  2. sounddevice records until silence or max_seconds
  3. faster-whisper transcribes offline
  4. Emits transcript_ready(text) signal

Runs entirely on a QThread to avoid blocking the UI.
The faster-whisper model is loaded once and cached.
"""

from __future__ import annotations

import logging
import queue
import tempfile
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000  # faster-whisper expects 16kHz
CHANNELS = 1


class VoiceListener(QObject):
    """
    Records audio on demand and emits transcribed text.
    Must be moved to a QThread before use.
    """

    recording_started = Signal()
    transcript_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._model = None  # lazy-loaded on first use
        self._is_recording = False
        self._lock = threading.Lock()

    def _load_model(self) -> bool:
        """Lazy-load the faster-whisper model. Returns True on success."""
        if self._model is not None:
            return True
        try:
            from faster_whisper import WhisperModel
            model_name = self._config.get("whisper_model", "tiny.en")
            logger.info("Loading faster-whisper model '%s'...", model_name)
            self._model = WhisperModel(model_name, device="cpu", compute_type="int8")
            logger.info("faster-whisper model loaded.")
            return True
        except Exception as exc:
            logger.error("Failed to load faster-whisper: %s", exc)
            self.error_occurred.emit(f"Whisper load failed: {exc}")
            return False

    def on_hotkey_pressed(self) -> None:
        """Slot: start recording. Ignores if already recording."""
        with self._lock:
            if self._is_recording:
                return
            self._is_recording = True

        if not self._load_model():
            with self._lock:
                self._is_recording = False
            return

        self.recording_started.emit()
        self._record_and_transcribe()

    def _record_and_transcribe(self) -> None:
        max_seconds = float(self._config.get("recording_max_seconds", 8))
        silence_thresh = float(self._config.get("silence_threshold_seconds", 1.5))
        max_frames = int(max_seconds * SAMPLE_RATE)
        silence_frames = int(silence_thresh * SAMPLE_RATE)

        audio_frames: list[np.ndarray] = []
        silent_count = 0
        SILENCE_AMPLITUDE = 0.01  # RMS below this = silence

        logger.debug("Recording started (max=%.1fs, silence=%.1fs).", max_seconds, silence_thresh)

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                dtype="float32", blocksize=1024) as stream:
                total = 0
                while total < max_frames:
                    chunk, _ = stream.read(1024)
                    audio_frames.append(chunk.copy())
                    total += len(chunk)

                    rms = float(np.sqrt(np.mean(chunk ** 2)))
                    if rms < SILENCE_AMPLITUDE:
                        silent_count += len(chunk)
                    else:
                        silent_count = 0

                    # Stop early if sustained silence after at least 1 second of audio
                    if total > SAMPLE_RATE and silent_count >= silence_frames:
                        logger.debug("Silence detected, stopping recording.")
                        break

        except Exception as exc:
            logger.error("sounddevice error: %s", exc)
            self.error_occurred.emit(f"Recording failed: {exc}")
            with self._lock:
                self._is_recording = False
            return

        if not audio_frames:
            with self._lock:
                self._is_recording = False
            return

        audio = np.concatenate(audio_frames, axis=0).flatten()
        self._transcribe(audio)

    def _transcribe(self, audio: np.ndarray) -> None:
        try:
            # faster-whisper accepts a numpy float32 array directly
            segments, _ = self._model.transcribe(audio, language="en", beam_size=1)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            logger.info("Transcribed: '%s'", text)
            if text:
                self.transcript_ready.emit(text)
            else:
                logger.debug("Empty transcription, ignoring.")
        except Exception as exc:
            logger.error("Transcription error: %s", exc)
            self.error_occurred.emit(f"Transcription failed: {exc}")
        finally:
            with self._lock:
                self._is_recording = False


class VoiceThread(QThread):
    """Convenience wrapper: owns VoiceListener and runs it on this thread."""

    recording_started = Signal()
    transcript_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._listener = VoiceListener(config)
        self._listener.moveToThread(self)
        self._listener.recording_started.connect(self.recording_started)
        self._listener.transcript_ready.connect(self.transcript_ready)
        self._listener.error_occurred.connect(self.error_occurred)

    def run(self) -> None:
        self.exec()  # Qt event loop so slots on this thread work

    def on_hotkey_pressed(self) -> None:
        # Call via queued connection from main thread
        self._listener.on_hotkey_pressed()

    def stop(self) -> None:
        self.quit()
        self.wait(3000)
