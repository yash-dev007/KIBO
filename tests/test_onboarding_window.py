"""
tests/test_onboarding_window.py — Unit tests for OnboardingWindow logic.

These tests exercise the non-UI parts of the onboarding: config persistence,
page state collection, and the was_completed flag.  They do NOT require a
display server because we patch QDialog.exec and avoid triggering paint events.
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ui.onboarding_window import OnboardingWindow, _build_welcome_page, _build_finish_page


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _qapp():
    """Create a QApplication once per test session (no display needed)."""
    from PySide6.QtWidgets import QApplication

    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    yield instance


@pytest.fixture()
def app(_qapp):
    """Ensure a QApplication exists for widget construction."""
    return _qapp


@pytest.fixture(autouse=True)
def _cleanup_widgets(app):
    yield
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()


@pytest.fixture()
def base_config() -> dict:
    return {
        "pet_name": "KIBO",
        "llm_provider": "auto",
        "groq_api_key_env": "GROQ_API_KEY",
        "ollama_base_url": "http://localhost:11434",
        "activation_hotkey": "ctrl+k",
        "clip_hotkey": "ctrl+alt+k",
        "piper_model": "en_US-amy-medium",
        "piper_models_dir": "models/piper",
        "memory_enabled": False,
        "proactive_enabled": False,
        "first_run_completed": False,
        "onboarding_version": "1.0",
    }


@pytest.fixture()
def temp_config_dir() -> Path:
    path = Path(__file__).parent.parent / ".test_tmp" / f"onboarding-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# OnboardingWindow construction
# ---------------------------------------------------------------------------

class TestOnboardingWindowConstruction:
    def test_instantiates_without_error(self, app, base_config):
        win = OnboardingWindow(base_config)
        assert win is not None
        win.close()

    def test_starts_on_first_page(self, app, base_config):
        win = OnboardingWindow(base_config)
        assert win._stack.currentIndex() == 0
        win.close()

    def test_was_completed_false_initially(self, app, base_config):
        win = OnboardingWindow(base_config)
        assert win.was_completed() is False
        win.close()

    def test_has_six_pages(self, app, base_config):
        win = OnboardingWindow(base_config)
        assert win._stack.count() == 6
        win.close()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

class TestNavigation:
    def test_back_button_disabled_on_first_page(self, app, base_config):
        win = OnboardingWindow(base_config)
        assert not win._back_btn.isEnabled()
        win.close()

    def test_next_advances_page(self, app, base_config):
        win = OnboardingWindow(base_config)
        win._go_next()
        assert win._stack.currentIndex() == 1
        win.close()

    def test_back_returns_to_previous_page(self, app, base_config):
        win = OnboardingWindow(base_config)
        win._go_next()
        win._go_back()
        assert win._stack.currentIndex() == 0
        win.close()

    def test_back_enabled_after_first_page(self, app, base_config):
        win = OnboardingWindow(base_config)
        win._go_next()
        assert win._back_btn.isEnabled()
        win.close()

    def test_next_button_says_finish_on_last_page(self, app, base_config):
        win = OnboardingWindow(base_config)
        last = win._stack.count() - 1
        win._stack.setCurrentIndex(last)
        win._update_nav_buttons()
        assert win._next_btn.text() == "Finish"
        win.close()

    def test_next_button_says_next_on_interior_pages(self, app, base_config):
        win = OnboardingWindow(base_config)
        win._stack.setCurrentIndex(2)
        win._update_nav_buttons()
        assert win._next_btn.text() == "Next"
        win.close()


# ---------------------------------------------------------------------------
# Provider state collection
# ---------------------------------------------------------------------------

class TestProviderState:
    def test_default_is_mock_provider(self, app, base_config):
        win = OnboardingWindow(base_config)
        state = win._get_provider_state()
        assert state.get("llm_provider") == "mock"
        win.close()


# ---------------------------------------------------------------------------
# Privacy state collection
# ---------------------------------------------------------------------------

class TestPrivacyState:
    def test_defaults_off(self, app, base_config):
        win = OnboardingWindow(base_config)
        state = win._get_privacy_state()
        assert state.get("memory_enabled") is False
        assert state.get("proactive_enabled") is False
        win.close()


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

class TestConfigPersistence:
    def test_finish_writes_first_run_completed(self, app, base_config, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text("{}", encoding="utf-8")

        dummy = MagicMock()
        dummy._get_provider_state = None
        dummy._get_privacy_state = None
        dummy._persist_config = lambda updates, raw_key: OnboardingWindow._persist_config(
            dummy, updates, raw_key
        )

        with patch("src.ui.onboarding_window.get_app_root", return_value=temp_config_dir):
            OnboardingWindow._finish(dummy)

        written = json.loads(config_file.read_text(encoding="utf-8"))
        assert written.get("first_run_completed") is True

    def test_finish_sets_was_completed_true(self, app, base_config, temp_config_dir):
        dummy = MagicMock()
        dummy._get_provider_state = None
        dummy._get_privacy_state = None
        dummy._completed = False
        dummy._persist_config = MagicMock()

        OnboardingWindow._finish(dummy)

        assert OnboardingWindow.was_completed(dummy) is True

    def test_persist_config_merges_with_existing(self, app, base_config, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text('{"pet_name": "TestPet"}', encoding="utf-8")

        dummy = MagicMock()
        dummy._get_provider_state = None
        dummy._get_privacy_state = None
        dummy._persist_config = lambda updates, raw_key: OnboardingWindow._persist_config(
            dummy, updates, raw_key
        )

        with patch("src.ui.onboarding_window.get_app_root", return_value=temp_config_dir):
            OnboardingWindow._finish(dummy)

        written = json.loads(config_file.read_text(encoding="utf-8"))
        assert written.get("pet_name") == "TestPet"
        assert written.get("first_run_completed") is True

    def test_groq_raw_key_not_persisted_to_config(self, app, base_config, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text("{}", encoding="utf-8")

        dummy = MagicMock()
        with patch("src.ui.onboarding_window.get_app_root", return_value=temp_config_dir):
            OnboardingWindow._persist_config(
                dummy,
                {**base_config, "first_run_completed": True},
                raw_groq_key="gsk_supersecret",
            )

        written = json.loads(config_file.read_text(encoding="utf-8"))
        assert "gsk_supersecret" not in json.dumps(written)
        assert "_groq_api_key_raw" not in written


# ---------------------------------------------------------------------------
# Page builders (smoke tests — no display required)
# ---------------------------------------------------------------------------

class TestPageBuilders:
    def test_welcome_page_creates_widget(self, app):
        page = _build_welcome_page()
        assert page is not None

    def test_finish_page_creates_widget(self, app):
        page = _build_finish_page()
        assert page is not None
