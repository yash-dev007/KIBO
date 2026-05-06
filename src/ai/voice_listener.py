"""
voice_listener.py — Record audio after hotkey, transcribe with faster-whisper.

Endpointing modes (`stt_vad_provider`):
  - "off"           — no endpointing, record until max_seconds.
  - "rms"           — RMS amplitude check; default, fully offline, no extra deps.
  - "silero_local"  — load silero-vad via torch.hub. NEVER chosen automatically;
                      requires explicit user consent because torch.hub fetches
                      the model from the network on first use.

Legacy `stt_use_vad` (bool) is honoured for back-compat: True maps to
"silero_local" only when no explicit `stt_vad_provider` is configured.

Default whisper model: base.en (more accurate than tiny.en, still
fast on CPU). Override via config["stt_model"] / config["whisper_model"].
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QMetaObject, QObject, QThread, Qt, Signal, Slot

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000  # faster-whisper expects 16kHz
CHANNELS = 1
VAD_FRAME_MS = 32  # silero-vad accepts 256/512/768 samples at 16kHz; 512 = 32ms

VALID_VAD_PROVIDERS = ("off", "rms", "silero_local")


def _resolve_vad_provider(config: dict) -> str:
    """Pick a VAD provider from config, honouring the legacy `stt_use_vad` flag.

    Resolution order:
      1. `stt_vad_provider` set explicitly to one of VALID_VAD_PROVIDERS → use it.
      2. Legacy `stt_use_vad` is True and no explicit provider → "silero_local".
      3. Legacy `stt_use_vad` is False and no explicit provider → "rms".
      4. Default → "rms" (offline-safe).
    """
    explicit = config.get("stt_vad_provider")
    if isinstance(explicit, str) and explicit in VALID_VAD_PROVIDERS:
        return explicit

    legacy = config.get("stt_use_vad")
    if isinstance(legacy, bool):
        return "silero_local" if legacy else "rms"

    return "rms"


class VoiceListener(QObject):
    """Records audio on demand and emits transcribed text."""

    recording_started = Signal()
    transcript_ready = Signal(str)
    no_speech_detected = Signal()
    error_occurred = Signal(str)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._whisper = None
        self._vad = None
        self._is_recording = False
        self._lock = threading.Lock()

        self._vad_provider = _resolve_vad_provider(config)
        self._use_vad = self._vad_provider == "silero_local"
        self._vad_threshold = float(config.get("stt_vad_threshold", 0.5))
        self._min_silence_ms = int(config.get("stt_min_silence_ms", 600))
        self._input_device = config.get("audio_input_device")  # None = system default

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
            self.error_occurred.emit(f"Whisper load failed: {exc}")
            return False

    def _load_vad(self) -> bool:
        if self._vad is not None:
            return True
        # Only "silero_local" triggers a torch.hub fetch — every other mode
        # (off, rms) stays fully offline and does not load anything.
        if self._vad_provider != "silero_local":
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
            self._vad_provider = "rms"
            self._use_vad = False
            return False

    @Slot()
    def warm_up(self) -> None:
        """Pre-load Whisper (and VAD if configured) on a quiet thread.

        Called shortly after first launch so the first recording does not
        pay the model-load cost at the moment the user expects speed.
        Failures are logged but not surfaced — warm-up is best-effort.
        """
        if self._whisper is None:
            try:
                self._load_whisper()
            except Exception as exc:
                logger.debug("Whisper warm-up failed: %s", exc)
        if self._vad_provider == "silero_local" and self._vad is None:
            try:
                self._load_vad()
            except Exception as exc:
                logger.debug("VAD warm-up failed: %s", exc)

    # ── Slot ────────────────────────────────────────────────────────────

    @Slot()
    def on_hotkey_pressed(self) -> None:
        """Slot: start recording. Ignores if already recording."""
        with self._lock:
            if self._is_recording:
                return
            self._is_recording = True

        if not self._load_whisper():
            with self._lock:
                self._is_recording = False
            return

        # Best-effort VAD load — silently degrades to RMS if missing.
        self._load_vad()

        self.recording_started.emit()
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
                device=self._input_device,
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
            self.error_occurred.emit(f"Recording failed: {exc}")
            return None

        if not audio_frames:
            return None
        return np.concatenate(audio_frames, axis=0).flatten()

    def _frame_is_speech(self, frame: np.ndarray) -> bool:
        """Decide if a single frame contains speech.

        Uses silero-vad when available (high accuracy); otherwise falls
        back to RMS amplitude check.
        """
        if self._vad is not None:
            try:
                import torch

                tensor = torch.from_numpy(frame.astype(np.float32))
                # silero-vad expects exactly 512 samples at 16kHz
                if tensor.shape[0] < 512:
                    return False
                prob = self._vad(tensor[:512], SAMPLE_RATE).item()
                return prob >= self._vad_threshold
            except Exception as exc:
                logger.debug("VAD error, switching to RMS: %s", exc)
                self._vad = None  # disable for the rest of the session

        rms = float(np.sqrt(np.mean(frame**2)))
        return rms >= 0.01

    # ── Transcription ───────────────────────────────────────────────────

    def _transcribe(self, audio: np.ndarray) -> None:
        try:
            segments, _ = self._whisper.transcribe(audio, language="en", beam_size=1)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            logger.info("Transcribed: '%s'", text)
            if text:
                self.transcript_ready.emit(text)
            else:
                # Distinct signal so the UI can render a friendly "I didn't
                # catch that — try again?" state instead of a generic error.
                self.no_speech_detected.emit()
                self.error_occurred.emit("No speech detected.")
        except Exception as exc:
            logger.error("Transcription error: %s", exc)
            self.error_occurred.emit(f"Transcription failed: {exc}")


class VoiceThread(QThread):
    """Convenience wrapper: owns VoiceListener and runs it on this thread."""

    recording_started = Signal()
    transcript_ready = Signal(str)
    no_speech_detected = Signal()
    error_occurred = Signal(str)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._listener = VoiceListener(config)
        self._listener.moveToThread(self)
        self._listener.recording_started.connect(self.recording_started)
        self._listener.transcript_ready.connect(self.transcript_ready)
        self._listener.no_speech_detected.connect(self.no_speech_detected)
        self._listener.error_occurred.connect(self.error_occurred)

    def run(self) -> None:
        self.exec()

    def on_hotkey_pressed(self) -> None:
        QMetaObject.invokeMethod(
            self._listener, "on_hotkey_pressed", Qt.QueuedConnection
        )

    def warm_up(self) -> None:
        QMetaObject.invokeMethod(self._listener, "warm_up", Qt.QueuedConnection)

    def stop(self) -> None:
        self.quit()
        self.wait(3000)
