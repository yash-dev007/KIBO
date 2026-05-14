"""TTS provider abstraction.

Selects the best available backend (Piper neural > pyttsx3 SAPI5)
based on config + what's installed.
"""

from __future__ import annotations

import logging

from .base import TTSProvider

logger = logging.getLogger(__name__)


def get_provider(config: dict) -> TTSProvider:
    """Resolve which TTS provider to use.

    Order when tts_provider == "auto":
      1. Piper (neural, local, ONNX)
      2. pyttsx3 (SAPI5, robotic but always works on Windows)

    Special values:
      "mock" — Silent provider that records speak() calls. For tests/CI only.
    """
    choice = config.get("tts_provider", "auto").lower()

    if choice == "mock":
        from .mock_provider import MockTTSProvider
        logger.info("TTS provider: Mock (silent, no audio)")
        return MockTTSProvider(config)

    if choice in ("piper", "auto"):
        provider = _try_piper(config)
        if provider is not None:
            logger.info("TTS provider: Piper (%s)", config.get("piper_model"))
            return provider
        if choice == "piper":
            raise RuntimeError("Piper requested but unavailable.")

    from .pyttsx3_provider import Pyttsx3Provider

    logger.info("TTS provider: pyttsx3 (SAPI5)")
    return Pyttsx3Provider(config)


def _try_piper(config: dict):
    try:
        from .piper_provider import PiperProvider
    except ImportError:
        logger.warning("Piper not installed (`pip install piper-tts`); falling back to pyttsx3.")
        return None

    try:
        return PiperProvider(config)
    except FileNotFoundError as exc:
        model = config.get("piper_model", "en_US-amy-medium")
        logger.warning(
            "Piper voice model '%s' not found. "
            "Download %s.onnx and %s.onnx.json from "
            "https://github.com/rhasspy/piper/releases and place them in '%s'. "
            "Falling back to pyttsx3.",
            model, model, model, config.get("piper_models_dir", "models/piper"),
        )
        return None
    except Exception as exc:
        logger.warning("Piper init failed: %s — falling back to pyttsx3.", exc)
        return None


__all__ = ["TTSProvider", "get_provider"]
