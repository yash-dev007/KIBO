"""
tests/test_config.py — Unit tests for config_manager.
"""

import json
import types
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config_manager import FileConfigManager, load_config, DEFAULT_CONFIG


@pytest.fixture
def tmp_config(tmp_path):
    """Returns a function that writes a config file and returns its path."""
    def _write(data: dict) -> str:
        p = tmp_path / "config.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)
    return _write


class TestLoadConfig:
    def test_returns_mapping_proxy(self, tmp_config):
        path = tmp_config({"pet_name": "KIBO"})
        cfg = load_config(path)
        assert isinstance(cfg, types.MappingProxyType)

    def test_immutable(self, tmp_config):
        path = tmp_config({"pet_name": "KIBO"})
        cfg = load_config(path)
        with pytest.raises(TypeError):
            cfg["pet_name"] = "other"

    def test_valid_config_loaded(self, tmp_config):
        path = tmp_config({"pet_name": "TestBot", "sleepy_hour": 22})
        cfg = load_config(path)
        assert cfg["pet_name"] == "TestBot"
        assert cfg["sleepy_hour"] == 22

    def test_missing_keys_use_defaults(self, tmp_config):
        path = tmp_config({"pet_name": "X"})
        cfg = load_config(path)
        assert cfg["cpu_panic_threshold"] == DEFAULT_CONFIG["cpu_panic_threshold"]
        assert cfg["poll_interval_ms"] == DEFAULT_CONFIG["poll_interval_ms"]

    def test_missing_file_uses_defaults(self, tmp_path):
        cfg = load_config(str(tmp_path / "nonexistent.json"))
        assert cfg["pet_name"] == DEFAULT_CONFIG["pet_name"]

    def test_malformed_json_uses_defaults(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        cfg = load_config(str(bad))
        assert cfg["pet_name"] == DEFAULT_CONFIG["pet_name"]

    def test_non_object_json_uses_defaults(self, tmp_path):
        arr = tmp_path / "arr.json"
        arr.write_text("[1, 2, 3]", encoding="utf-8")
        cfg = load_config(str(arr))
        assert cfg["pet_name"] == DEFAULT_CONFIG["pet_name"]

    def test_unknown_keys_preserved(self, tmp_config):
        path = tmp_config({"pet_name": "KIBO", "my_custom_key": "hello"})
        cfg = load_config(path)
        assert cfg["my_custom_key"] == "hello"

    def test_partial_config_merges_correctly(self, tmp_config):
        path = tmp_config({"cpu_panic_threshold": 70})
        cfg = load_config(path)
        assert cfg["cpu_panic_threshold"] == 70
        assert cfg["pet_name"] == DEFAULT_CONFIG["pet_name"]

    def test_invalid_window_size_resets(self, tmp_config):
        path = tmp_config({"window_size": "bad"})
        cfg = load_config(path)
        assert cfg["window_size"] == [200, 200]

    def test_invalid_int_key_resets(self, tmp_config):
        path = tmp_config({"poll_interval_ms": "fast"})
        cfg = load_config(path)
        assert cfg["poll_interval_ms"] == DEFAULT_CONFIG["poll_interval_ms"]


class TestFileConfigManager:
    def test_update_config_persists_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.config_manager.get_app_root", lambda: tmp_path)
        (tmp_path / "config.json").write_text(
            json.dumps({"pet_name": "KIBO", "tts_enabled": True}),
            encoding="utf-8",
        )

        manager = FileConfigManager()
        updated = manager.update_config({"tts_enabled": False, "buddy_skin": "capy"})

        saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert updated["tts_enabled"] is False
        assert saved["tts_enabled"] is False
        assert saved["buddy_skin"] == "capy"

    def test_update_config_validates_values(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.config_manager.get_app_root", lambda: tmp_path)
        manager = FileConfigManager()

        updated = manager.update_config({"buddy_skin": "BAD SKIN!"})

        assert updated["buddy_skin"] == DEFAULT_CONFIG["buddy_skin"]


class TestNewConfigKeys:
    def test_repo_config_keys_are_known(self):
        config_path = Path(__file__).parent.parent / "config.json"
        repo_config = json.loads(config_path.read_text(encoding="utf-8"))
        unknown = sorted(set(repo_config) - set(DEFAULT_CONFIG))
        assert unknown == []

    def test_buddy_skin_default(self, tmp_config):
        path = tmp_config({})
        cfg = load_config(path)
        assert cfg["buddy_skin"] == "skales"

    def test_buddy_skin_custom(self, tmp_config):
        path = tmp_config({"buddy_skin": "capy"})
        cfg = load_config(path)
        assert cfg["buddy_skin"] == "capy"

    def test_invalid_buddy_skin_resets(self, tmp_config):
        path = tmp_config({"buddy_skin": 123})
        cfg = load_config(path)
        assert cfg["buddy_skin"] == "skales"

    def test_buddy_skin_invalid_chars_resets(self, tmp_config):
        path = tmp_config({"buddy_skin": "UPPER CASE!"})
        cfg = load_config(path)
        assert cfg["buddy_skin"] == "skales"

    def test_idle_action_intervals_default(self, tmp_config):
        path = tmp_config({})
        cfg = load_config(path)
        assert cfg["idle_action_interval_min_s"] == 30
        assert cfg["idle_action_interval_max_s"] == 60

    def test_idle_action_invalid_min_resets(self, tmp_config):
        path = tmp_config({"idle_action_interval_min_s": -5})
        cfg = load_config(path)
        assert cfg["idle_action_interval_min_s"] == 30

    def test_idle_action_min_gte_max_resets(self, tmp_config):
        path = tmp_config({"idle_action_interval_min_s": 60, "idle_action_interval_max_s": 30})
        cfg = load_config(path)
        assert cfg["idle_action_interval_min_s"] == 30
        assert cfg["idle_action_interval_max_s"] == 60


class TestOnboardingConfigKeys:
    def test_first_run_defaults_false(self, tmp_config):
        """first_run_completed must default to False for a fresh install."""
        path = tmp_config({})
        cfg = load_config(path)
        assert cfg["first_run_completed"] is False

    def test_onboarding_version_present(self, tmp_config):
        """onboarding_version must be present in the default config."""
        path = tmp_config({})
        cfg = load_config(path)
        assert "onboarding_version" in cfg
        assert cfg["onboarding_version"] == "1.0"

    def test_first_run_completed_can_be_set_true(self, tmp_config):
        """Config file can override first_run_completed to True."""
        path = tmp_config({"first_run_completed": True})
        cfg = load_config(path)
        assert cfg["first_run_completed"] is True

    def test_onboarding_version_in_default_config(self):
        """DEFAULT_CONFIG must declare onboarding_version."""
        assert "onboarding_version" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["onboarding_version"] == "1.0"
