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
    "system_prompt": (
        "You are KIBO, a helpful virtual pet assistant who lives on the user's desktop. "
        "Be concise, friendly, and slightly playful. Keep responses to 2-3 sentences "
        "unless the user asks for more detail."
    ),
    "conversation_history_limit": 10,
    "tts_enabled": True,
    "tts_rate": 175,
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
    "opaque_fallback": False,
    "buddy_skin": "skales",
    "idle_action_interval_min_s": 8,
    "idle_action_interval_max_s": 20,
    "memory_enabled": True,
    "memory_model": "qwen2.5-coder:7b",
    "memory_max_facts": 200,
    "proactive_enabled": True,
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
                    "quiet_hours_start", "quiet_hours_end"):
        if not isinstance(cfg.get(int_key), int):
            default_val = DEFAULT_CONFIG[int_key]
            logger.warning("'%s' must be an int. Resetting to %s.", int_key, default_val)
            cfg[int_key] = default_val

    for float_key in ("silence_threshold_seconds", "recording_max_seconds"):
        if not isinstance(cfg.get(float_key), (int, float)):
            default_val = DEFAULT_CONFIG[float_key]
            logger.warning("'%s' must be a number. Resetting to %s.", float_key, default_val)
            cfg[float_key] = default_val
            
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
