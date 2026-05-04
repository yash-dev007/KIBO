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
