"""
tests/test_provider_health.py — Unit tests for src/system/provider_health.py.

All tests are offline-safe: no real network calls, no audio hardware required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch

from src.system.provider_health import (
    check_audio_output,
    check_groq,
    check_hotkey,
    check_ollama,
    check_piper,
    check_piper_package,
)


# ---------------------------------------------------------------------------
# check_groq
# ---------------------------------------------------------------------------

class TestCheckGroq:
    def test_no_key_returns_unavailable(self) -> None:
        result = check_groq(None)
        assert result["available"] is False
        assert result["reason"]

    def test_empty_string_returns_unavailable(self) -> None:
        result = check_groq("")
        assert result["available"] is False

    def test_bad_format_returns_unavailable(self) -> None:
        result = check_groq("badkey")
        assert result["available"] is False
        assert "invalid" in result["reason"].lower()

    def test_valid_format_returns_available(self) -> None:
        result = check_groq("gsk_abc123")
        assert result["available"] is True
        assert result["reason"]

    def test_valid_format_longer_key(self) -> None:
        result = check_groq("gsk_" + "x" * 50)
        assert result["available"] is True


# ---------------------------------------------------------------------------
# check_piper
# ---------------------------------------------------------------------------

class TestCheckPiper:
    def test_none_path_returns_unavailable(self) -> None:
        result = check_piper(None)
        assert result["available"] is False
        assert result["reason"]

    def test_nonexistent_file_returns_unavailable(self) -> None:
        result = check_piper("/nonexistent/path/model.onnx")
        assert result["available"] is False
        assert "not found" in result["reason"].lower()

    def test_existing_file_returns_available(self, tmp_path: Path) -> None:
        model_file = tmp_path / "en_US-amy-medium.onnx"
        model_file.write_bytes(b"fake model data")
        result = check_piper(str(model_file))
        assert result["available"] is True
        assert result["reason"]


# ---------------------------------------------------------------------------
# check_ollama
# ---------------------------------------------------------------------------

class TestCheckOllama:
    def test_unreachable_host_returns_unavailable(self) -> None:
        # Port 1 is reserved and will always refuse connections immediately
        result = check_ollama("http://localhost:1")
        assert result["available"] is False
        assert result["reason"]

    def test_invalid_host_returns_unavailable(self) -> None:
        result = check_ollama("http://192.0.2.0:11434")  # TEST-NET — never routed
        assert result["available"] is False


# ---------------------------------------------------------------------------
# check_audio_output
# ---------------------------------------------------------------------------

class TestCheckAudioOutput:
    def test_returns_available_when_outputs_exist(self) -> None:
        fake_devices = [
            {"name": "Speakers", "max_output_channels": 2, "max_input_channels": 0},
            {"name": "Mic", "max_output_channels": 0, "max_input_channels": 1},
        ]
        with patch("sounddevice.query_devices", return_value=fake_devices):
            result = check_audio_output()
        assert result["available"] is True
        assert "1" in result["reason"]  # one output device found

    def test_returns_unavailable_with_no_outputs(self) -> None:
        fake_devices = [
            {"name": "Mic", "max_output_channels": 0, "max_input_channels": 1},
        ]
        with patch("sounddevice.query_devices", return_value=fake_devices):
            result = check_audio_output()
        assert result["available"] is False
        assert "No audio output" in result["reason"]

    def test_handles_query_devices_error(self) -> None:
        with patch("sounddevice.query_devices", side_effect=RuntimeError("no devices")):
            result = check_audio_output()
        assert result["available"] is False
        assert "no devices" in result["reason"]


# ---------------------------------------------------------------------------
# check_piper_package
# ---------------------------------------------------------------------------

class TestCheckPiperPackage:
    def test_returns_unavailable_on_import_error(self) -> None:
        with patch("importlib.import_module", side_effect=ImportError("no module piper")):
            result = check_piper_package()
        assert result["available"] is False
        assert "not installed" in result["reason"]

    def test_returns_available_when_importable(self) -> None:
        with patch("importlib.import_module", return_value=object()):
            result = check_piper_package()
        assert result["available"] is True


# ---------------------------------------------------------------------------
# check_hotkey
# ---------------------------------------------------------------------------

class TestCheckHotkey:
    def test_none_returns_unavailable(self) -> None:
        result = check_hotkey(None)
        assert result["available"] is False

    def test_empty_string_returns_unavailable(self) -> None:
        assert check_hotkey("")["available"] is False

    def test_valid_hotkey_returns_available(self) -> None:
        result = check_hotkey("ctrl+k")
        assert result["available"] is True

    def test_invalid_hotkey_returns_unavailable(self) -> None:
        # An obviously malformed hotkey string
        result = check_hotkey("ctrl++")
        assert result["available"] is False
