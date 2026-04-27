"""Piper TTS provider — neural, local, ONNX-based.

Streams 22050Hz int16 PCM directly to sounddevice. Way faster and
warmer than SAPI5; first audio sample typically <150ms after `speak()`.

Voice models: download from https://github.com/rhasspy/piper/releases
and drop .onnx + .onnx.json into config["piper_models_dir"].
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PiperProvider:
    def __init__(self, config: dict) -> None:
        from piper.voice import PiperVoice  # raises ImportError if missing

        self._voice_name = config.get("piper_model", "en_US-amy-medium")
        models_dir = Path(config.get("piper_models_dir", "models/piper")).expanduser()
        if not models_dir.is_absolute():
            from src.core.config_manager import get_app_root

            models_dir = get_app_root() / models_dir

        model_path = models_dir / f"{self._voice_name}.onnx"
        config_path = models_dir / f"{self._voice_name}.onnx.json"

        if not model_path.exists():
            raise FileNotFoundError(
                f"Piper voice not found: {model_path}. "
                f"Download from https://github.com/rhasspy/piper/releases"
            )

        self._voice = PiperVoice.load(str(model_path), config_path=str(config_path))
        self._sample_rate = self._voice.config.sample_rate
        self._stop_event = threading.Event()

        # sounddevice imported lazily so we don't double-init audio if pyttsx3 is also alive.
        import sounddevice as sd

        self._sd = sd
        self._stream: Optional[sd.OutputStream] = None

    def is_available(self) -> bool:
        return self._voice is not None

    def speak(self, text: str) -> None:
        if not text.strip():
            return

        self._stop_event.clear()
        try:
            stream = self._sd.OutputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
            )
            stream.start()
            self._stream = stream

            # synthesize_stream_raw yields PCM bytes as Piper generates.
            for audio_chunk in self._voice.synthesize_stream_raw(text):
                if self._stop_event.is_set():
                    break
                # Convert raw bytes -> int16 array for sounddevice
                import numpy as np

                samples = np.frombuffer(audio_chunk, dtype=np.int16)
                stream.write(samples)

            stream.stop()
            stream.close()
        except Exception as exc:
            logger.error("Piper speak error: %s", exc)
        finally:
            self._stream = None

    def stop(self) -> None:
        self._stop_event.set()
        stream = self._stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass
