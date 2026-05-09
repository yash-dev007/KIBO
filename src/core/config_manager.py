"""
config_manager.py — Load and validate config.json with safe defaults.
Returns an immutable MappingProxyType so config is never mutated at runtime.
"""

import sys
import json
import re
import types
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_app_root() -> Path:
    """
    Root for user-editable files (config.json) — always next to the EXE.
    In dev mode, returns the project directory.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent.absolute()


def get_bundle_dir() -> Path:
    """
    Root for bundled read-only assets (PNG frames, etc.).
    In PyInstaller builds, sys._MEIPASS points to the _internal/ folder
    where datas are extracted. In dev mode, same as get_app_root().
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent.absolute()


def get_user_data_dir() -> Path:
    """User data directory — persists across reinstalls."""
    d = Path.home() / ".kibo"
    d.mkdir(parents=True, exist_ok=True)
    return d


DEFAULT_CONFIG: dict = {
    "pet_name": "KIBO",
    "ai_enabled": True,
    "activation_hotkey": "ctrl+k",
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "qwen2.5-coder:7b",
    "ollama_timeout_s": 60.0,
    "llm_provider": "auto",
    "groq_api_key_env": "GROQ_API_KEY",
    "groq_model": "llama-3.3-70b-versatile",
    "groq_timeout_s": 30.0,
    "system_prompt": (
        "You are KIBO, a helpful virtual pet assistant who lives on the user's desktop. "
        "Be concise, friendly, and slightly playful. Keep responses to 2-3 sentences "
        "unless the user asks for more detail."
    ),
    "conversation_history_limit": 10,
    "tts_enabled": True,
    "tts_provider": "auto",
    "tts_rate": 175,
    "piper_model": "en_US-amy-medium",
    "piper_models_dir": "models/piper",
    "poll_interval_ms": 3000,
    "cpu_panic_threshold": 80,
    "battery_tired_threshold": 20,
    "sleepy_hour": 23,
    "studious_windows": ["Visual Studio Code", "code"],
    "frame_rate_ms": 150,
    "window_size": [200, 200],
    "enable_speech_bubbles": True,
    "speech_bubble_timeout_ms": 5000,
    "recording_max_seconds": 8,
    "silence_threshold_seconds": 1.5,
    "whisper_model": "tiny.en",
    "stt_model": "base.en",
    "stt_use_vad": True,
    "stt_vad_provider": "rms",  # "off" | "rms" | "silero_local" — silero requires consent
    "stt_vad_threshold": 0.5,
    "stt_min_silence_ms": 600,
    "audio_input_device": None,  # None = system default; int or device-name string
    "audio_output_device": None,
    "voice_warmup_on_launch": True,
    "opaque_fallback": False,
    "buddy_skin": "skales",
    "idle_action_interval_min_s": 30,
    "idle_action_interval_max_s": 60,
    "memory_enabled": True,
    "memory_model": "qwen2.5-coder:7b",
    "memory_max_facts": 200,
    "memory_provider": "auto",
    "memory_top_k": 5,
    "memory_extraction_inline": True,
    "proactive_enabled": False,
    "quiet_hours_start": 22,
    "quiet_hours_end": 7,
    "notification_types": {
        "morning-greeting": True,
        "idle-checkin": True,
        "eod-summary": True,
        "cpu-panic": True,
        "battery-low": True,
        "meeting-reminder": True,
        "email-alert": True,
        "task-blocked": True
    },
    "calendar_provider": "none",
    "calendar_lookahead_minutes": 60,
    "clip_hotkey": "ctrl+alt+k",
    "demo_mode": False,
    "demo_llm_responses": ["Mock response."],
    "demo_llm_delay_ms": 0,
    "demo_proactive_idle_minutes": 1,
    "demo_seed_memory": "",
    "diagnostics_include_memories": False,
    "personality_version": "1.0",
    "safety_version": "1.0",
    "first_run_completed": False,
    "onboarding_version": "1.0",
}

_SKIN_PATTERN = re.compile(r"^[a-z0-9_-]+$")


def load_config(path: str = "config.json") -> types.MappingProxyType:
    """
    Load config from the given JSON path and merge with DEFAULT_CONFIG.
    The path is resolved relative to the app root.
    """
    app_root = get_app_root()
    config_path = app_root / path
    merged = dict(DEFAULT_CONFIG)

    if not config_path.exists():
        logger.warning("config.json not found at '%s', using defaults.", config_path)
        return types.MappingProxyType(merged)

    try:
        with config_path.open("r", encoding="utf-8") as f:
            user_config = json.load(f)
    except json.JSONDecodeError as exc:
        logger.error("Malformed config.json: %s — using defaults.", exc)
        return types.MappingProxyType(merged)

    if not isinstance(user_config, dict):
        logger.error("config.json must be a JSON object, got %s — using defaults.", type(user_config))
        return types.MappingProxyType(merged)

    # Warn about unexpected keys (typos etc.) but still accept them
    known_keys = set(DEFAULT_CONFIG.keys())
    for key in user_config:
        if key not in known_keys:
            logger.warning("Unknown config key '%s' — keeping it anyway.", key)

    merged.update(user_config)

    # Validate critical types
    _validate(merged)

    return types.MappingProxyType(merged)


class FileConfigManager:
    """Mutable config facade used by the FastAPI settings endpoint.

    `load_config()` intentionally returns an immutable mapping for runtime
    safety. The API layer still needs a controlled write path for Electron
    settings, so this class owns the merge, validation, and JSON persistence.
    """

    def __init__(self, path: str = "config.json") -> None:
        self._path = path
        self._config: dict[str, Any] = dict(load_config(path))

    @property
    def path(self) -> Path:
        return get_app_root() / self._path

    def get_config(self) -> dict[str, Any]:
        return dict(self._config)

    def update_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise TypeError("Config patch must be a dict")

        next_config = dict(self._config)
        next_config.update(patch)
        _validate(next_config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(next_config, f, indent=4)
            f.write("\n")
        self._config = next_config
        return self.get_config()


def _validate(cfg: dict) -> None:
    """Log warnings for obviously wrong config values. Never raise."""
    if not isinstance(cfg.get("window_size"), list) or len(cfg["window_size"]) != 2:
        logger.warning("window_size must be a list of [width, height]. Resetting to [200, 200].")
        cfg["window_size"] = [200, 200]

    if not isinstance(cfg.get("studious_windows"), list):
        logger.warning("studious_windows must be a list. Resetting to [].")
        cfg["studious_windows"] = []

    for int_key in ("poll_interval_ms", "frame_rate_ms", "speech_bubble_timeout_ms",
                    "cpu_panic_threshold", "sleepy_hour", "tts_rate",
                    "conversation_history_limit", "battery_tired_threshold",
                    "quiet_hours_start", "quiet_hours_end", "stt_min_silence_ms",
                    "memory_max_facts", "memory_top_k"):
        if not isinstance(cfg.get(int_key), int):
            default_val = DEFAULT_CONFIG[int_key]
            logger.warning("'%s' must be an int. Resetting to %s.", int_key, default_val)
            cfg[int_key] = default_val

    for float_key in ("silence_threshold_seconds", "recording_max_seconds",
                      "ollama_timeout_s", "groq_timeout_s", "stt_vad_threshold"):
        if not isinstance(cfg.get(float_key), (int, float)):
            default_val = DEFAULT_CONFIG[float_key]
            logger.warning("'%s' must be a number. Resetting to %s.", float_key, default_val)
            cfg[float_key] = default_val

    for bool_key in ("stt_use_vad", "memory_extraction_inline", "demo_mode",
                     "diagnostics_include_memories", "proactive_enabled"):
        if not isinstance(cfg.get(bool_key), bool):
            default_val = DEFAULT_CONFIG[bool_key]
            logger.warning("'%s' must be a bool. Resetting to %s.", bool_key, default_val)
            cfg[bool_key] = default_val
            
    if not isinstance(cfg.get("notification_types"), dict):
        logger.warning("'notification_types' must be a dict. Resetting to default.")
        cfg["notification_types"] = dict(DEFAULT_CONFIG["notification_types"])

    # Validate buddy_skin
    skin = cfg.get("buddy_skin")
    if not isinstance(skin, str) or not _SKIN_PATTERN.match(skin):
        logger.warning("buddy_skin must be a lowercase alphanumeric string. Resetting to 'skales'.")
        cfg["buddy_skin"] = DEFAULT_CONFIG["buddy_skin"]

    # Validate idle action intervals
    min_s = cfg.get("idle_action_interval_min_s")
    max_s = cfg.get("idle_action_interval_max_s")
    if not isinstance(min_s, (int, float)) or min_s <= 0:
        logger.warning("idle_action_interval_min_s must be a positive number. Resetting to 30.")
        cfg["idle_action_interval_min_s"] = DEFAULT_CONFIG["idle_action_interval_min_s"]
        min_s = cfg["idle_action_interval_min_s"]
    if not isinstance(max_s, (int, float)) or max_s <= 0:
        logger.warning("idle_action_interval_max_s must be a positive number. Resetting to 60.")
        cfg["idle_action_interval_max_s"] = DEFAULT_CONFIG["idle_action_interval_max_s"]
        max_s = cfg["idle_action_interval_max_s"]
    if min_s >= max_s:
        logger.warning("idle_action_interval_min_s must be < max_s. Resetting both to defaults.")
        cfg["idle_action_interval_min_s"] = DEFAULT_CONFIG["idle_action_interval_min_s"]
        cfg["idle_action_interval_max_s"] = DEFAULT_CONFIG["idle_action_interval_max_s"]
