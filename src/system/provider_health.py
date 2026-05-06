"""
provider_health.py — Lightweight health-probe functions for KIBO providers.

All probes return {"available": bool, "reason": str}.
None of these probes send user content to any external service.
"""

from __future__ import annotations


def check_groq(api_key: str | None) -> dict:
    """Check if a Groq API key is present and matches the expected format.

    Does NOT make any network request.
    """
    if not api_key:
        return {"available": False, "reason": "No API key configured"}
    if not isinstance(api_key, str) or not api_key.startswith("gsk_"):
        return {"available": False, "reason": "API key format looks invalid"}
    return {"available": True, "reason": "API key present"}


def check_ollama(host: str = "http://localhost:11434") -> dict:
    """Check if an Ollama server is reachable at the given host.

    Sends a short-timeout GET to /api/tags — no user content is transmitted.
    """
    url = f"{host.rstrip('/')}/api/tags"
    try:
        import requests  # optional dep; guarded by try/except

        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            return {"available": True, "reason": "Ollama responded"}
        return {"available": False, "reason": f"HTTP {response.status_code}"}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def check_piper(model_path: str | None) -> dict:
    """Check if a Piper TTS model file exists at the given path."""
    from pathlib import Path

    if not model_path:
        return {"available": False, "reason": "No Piper model path configured"}
    path = Path(model_path)
    if path.exists():
        return {"available": True, "reason": f"Model found at {path}"}
    return {"available": False, "reason": f"Model not found at {path}"}


def check_microphone() -> dict:
    """Check if at least one audio input device is available via PyAudio."""
    try:
        import pyaudio  # optional dep; guarded by try/except

        pa = pyaudio.PyAudio()
        count = pa.get_device_count()
        pa.terminate()
        if count > 0:
            return {"available": True, "reason": f"{count} audio device(s) found"}
        return {"available": False, "reason": "No audio input devices found"}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def check_audio_output() -> dict:
    """Check if at least one audio output device is reachable.

    Uses sounddevice's host API to list output devices. No audio is played.
    """
    try:
        import sounddevice as sd  # optional dep; guarded by try/except

        devices = sd.query_devices()
        outputs = [
            d for d in devices if isinstance(d, dict) and d.get("max_output_channels", 0) > 0
        ]
        if outputs:
            return {
                "available": True,
                "reason": f"{len(outputs)} output device(s) found",
            }
        return {"available": False, "reason": "No audio output devices found"}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def check_piper_package() -> dict:
    """Check whether the `piper` Python package is importable.

    Distinguishes a missing package from a missing voice model so the
    Settings UI can guide the user to the right fix.
    """
    try:
        import importlib

        importlib.import_module("piper")
        return {"available": True, "reason": "piper package importable"}
    except ImportError as exc:
        return {"available": False, "reason": f"piper package not installed: {exc}"}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def check_hotkey(hotkey: str | None) -> dict:
    """Check whether a hotkey string can be parsed by the keyboard library.

    Does NOT register the hotkey — purely a syntactic validation so Settings
    can warn before the user saves a typo.
    """
    if not hotkey or not isinstance(hotkey, str):
        return {"available": False, "reason": "Hotkey not configured"}
    try:
        import keyboard  # optional dep; guarded by try/except

        keyboard.parse_hotkey(hotkey)
        return {"available": True, "reason": f"'{hotkey}' is a valid hotkey"}
    except ValueError as exc:
        return {"available": False, "reason": f"Invalid hotkey '{hotkey}': {exc}"}
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
