"""
voice_listener.py — Record audio after hotkey, transcribe with faster-whisper.

Endpointing:
  - silero-vad (when stt_use_vad=true and the package is installed) for
    accurate end-of-speech detection — usually 200-400ms after the user
    stops talking.
  - Falls back to RMS-based silence detection when VAD isn't available.

Default whisper model: base.en (more accurate than tiny.en, still
fast on CPU). Override via config["stt_model"] / config["whisper_model"].
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
VAD_FRAME_MS = 32  # silero-vad accepts 512 samples at 16kHz (32ms)


class VoiceListener:
    """Records audio on demand and emits EventBus events with transcribed text."""

    def __init__(self, config: dict, event_bus=None) -> None:
        self._config = config
        self._event_bus = event_bus
        self._whisper = None
        self._vad = None
        self._is_recording = False
        self._lock = threading.Lock()

        self._use_vad = bool(config.get("stt_use_vad", True))
        self._vad_threshold = float(config.get("stt_vad_threshold", 0.5))
        self._min_silence_ms = int(config.get("stt_min_silence_ms", 600))

    # ── Lazy loaders ────────────────────────────────────────────────────

    def _load_whisper(self) -> bool:
        if self._whisper is not None:
            return True
        try:
            from faster_whisper import WhisperModel

            model_name = self._config.get(
                "stt_model", self._config.get("whisper_model", "base.en")
            )
            logger.info("Loading faster-whisper model '%s'...", model_name)
            self._whisper = WhisperModel(model_name, device="cpu", compute_type="int8")
            logger.info("faster-whisper model loaded.")
            return True
        except Exception as exc:
            logger.error("Failed to load faster-whisper: %s", exc)
            if self._event_bus:
                self._event_bus.emit("error_occurred", f"Whisper load failed: {exc}")
            return False

    def _load_vad(self) -> bool:
        if self._vad is not None:
            return True
        if not self._use_vad:
            return False
        try:
            import torch

            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                trust_repo=True,
                onnx=False,
            )
            self._vad = model
            logger.info("silero-vad loaded.")
            return True
        except Exception as exc:
            logger.warning("silero-vad unavailable (%s); using RMS fallback.", exc)
            self._use_vad = False
            return False

    # ── Entry point ────────────────────────────────────────────────────

    def on_hotkey_pressed(self) -> None:
        with self._lock:
            if self._is_recording:
                return
            self._is_recording = True

        if not self._load_whisper():
            with self._lock:
                self._is_recording = False
            return

        self._load_vad()

        if self._event_bus:
            self._event_bus.emit("recording_started")
        try:
            audio = self._record()
            if audio is not None and audio.size > 0:
                self._transcribe(audio)
        finally:
            with self._lock:
                self._is_recording = False

    # ── Recording ───────────────────────────────────────────────────────

    def _record(self) -> Optional[np.ndarray]:
        max_seconds = float(self._config.get("recording_max_seconds", 8))
        max_frames = int(max_seconds * SAMPLE_RATE)
        frame_samples = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)
        min_silence_frames = int(self._min_silence_ms * SAMPLE_RATE / 1000)

        audio_frames: list[np.ndarray] = []
        silent_count = 0
        total = 0
        speech_seen = False

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=frame_samples,
            ) as stream:
                while total < max_frames:
                    chunk, _ = stream.read(frame_samples)
                    audio_frames.append(chunk.copy())
                    total += len(chunk)

                    is_speech = self._frame_is_speech(chunk.flatten())
                    if is_speech:
                        speech_seen = True
                        silent_count = 0
                    else:
                        silent_count += len(chunk)

                    if speech_seen and silent_count >= min_silence_frames:
                        logger.debug("Endpoint detected, stopping.")
                        break
        except Exception as exc:
            logger.error("sounddevice error: %s", exc)
            if self._event_bus:
                self._event_bus.emit("error_occurred", f"Recording failed: {exc}")
            return None

        if not audio_frames:
            return None
        return np.concatenate(audio_frames, axis=0).flatten()

    def _frame_is_speech(self, frame: np.ndarray) -> bool:
        if self._vad is not None:
            try:
                import torch

                tensor = torch.from_numpy(frame.astype(np.float32))
                if tensor.shape[0] < 512:
                    return False
                prob = self._vad(tensor[:512], SAMPLE_RATE).item()
                return prob >= self._vad_threshold
            except Exception as exc:
                logger.debug("VAD error, switching to RMS: %s", exc)
                self._vad = None

        rms = float(np.sqrt(np.mean(frame**2)))
        return rms >= 0.01

    # ── Transcription ───────────────────────────────────────────────────

    def _transcribe(self, audio: np.ndarray) -> None:
        try:
            segments, _ = self._whisper.transcribe(audio, language="en", beam_size=1)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            logger.info("Transcribed: '%s'", text)
            if text:
                if self._event_bus:
                    self._event_bus.emit("transcript_ready", text)
            else:
                if self._event_bus:
                    self._event_bus.emit("error_occurred", "No speech detected.")
        except Exception as exc:
            logger.error("Transcription error: %s", exc)
            if self._event_bus:
                self._event_bus.emit("error_occurred", f"Transcription failed: {exc}")


class VoiceThread(threading.Thread):
    """Daemon thread that owns a VoiceListener and processes hotkey requests via a queue."""

    def __init__(self, config: dict, event_bus=None) -> None:
        super().__init__(daemon=True)
        self._listener = VoiceListener(config, event_bus=event_bus)
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.1)
                try:
                    if task == "hotkey_pressed":
                        self._listener.on_hotkey_pressed()
                finally:
                    self._queue.task_done()
            except queue.Empty:
                continue

    def on_hotkey_pressed(self) -> None:
        self._queue.put("hotkey_pressed")

    def stop(self) -> None:
        self._stop_event.set()
