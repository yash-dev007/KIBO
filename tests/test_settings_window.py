from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.config_manager import DEFAULT_CONFIG
from src.ui.settings_window import SettingsWindow


@pytest.fixture(scope="session")
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _health_patches():
    with patch("src.ui.settings_window.check_ollama", return_value={"available": False, "reason": "offline"}), \
         patch("src.ui.settings_window.check_microphone", return_value={"available": False, "reason": "no mic"}), \
         patch("src.ui.settings_window.check_audio_output", return_value={"available": False, "reason": "no output"}), \
         patch("src.ui.settings_window.check_piper_package", return_value={"available": False, "reason": "no piper"}), \
         patch("src.ui.settings_window.check_piper", return_value={"available": False, "reason": "no model"}):
        yield


def test_settings_has_required_product_tabs(app) -> None:
    win = SettingsWindow(dict(DEFAULT_CONFIG))
    tabs = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    assert "General" in tabs
    assert "Voice" in tabs
    assert "AI" in tabs
    assert "Notifications" in tabs
    assert "Memory" in tabs
    assert "Data" in tabs
    win.close()


def test_parse_optional_device() -> None:
    assert SettingsWindow._parse_optional_device("") is None
    assert SettingsWindow._parse_optional_device("3") == 3
    assert SettingsWindow._parse_optional_device("Focusrite USB") == "Focusrite USB"


def test_reset_current_voice_tab_restores_defaults(app) -> None:
    win = SettingsWindow(dict(DEFAULT_CONFIG))
    index = [win.tabs.tabText(i) for i in range(win.tabs.count())].index("Voice")
    win.tabs.setCurrentIndex(index)
    win.f_stt_vad_provider.setCurrentText("silero_local")
    win.f_audio_input_device.setText("7")

    win._reset_current_tab()

    assert win.f_stt_vad_provider.currentText() == DEFAULT_CONFIG["stt_vad_provider"]
    assert win.f_audio_input_device.text() == ""
    win.close()
