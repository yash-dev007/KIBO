"""Diagnostics export for KIBO.

The diagnostic payload is intentionally boring: system/app metadata, redacted
config, provider health, and recent log file names. It excludes raw prompts,
transcripts, and memory contents unless a caller explicitly opts in.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.config_manager import get_user_data_dir
from src.system.provider_health import (
    check_audio_output,
    check_groq,
    check_hotkey,
    check_microphone,
    check_ollama,
    check_piper,
    check_piper_package,
)

SECRET_KEY_MARKERS = ("key", "token", "secret", "password", "credential")


def redact_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a config copy safe for diagnostics."""
    redacted: dict[str, Any] = {}
    for key, value in config.items():
        lower = key.lower()
        if any(marker in lower for marker in SECRET_KEY_MARKERS):
            redacted[key] = "<redacted>" if value else value
        elif lower in {"system_prompt"}:
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted


def collect_diagnostics(config: dict[str, Any], include_memories: bool = False) -> dict[str, Any]:
    """Collect a deterministic diagnostics payload without user conversation text."""
    piper_model = config.get("piper_model", "")
    piper_dir = config.get("piper_models_dir", "models/piper")
    piper_path = str(Path(piper_dir) / f"{piper_model}.onnx") if piper_model else None
    data_dir = get_user_data_dir()
    logs_dir = data_dir / "logs"

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "app": {
            "name": "KIBO",
            "personality_version": config.get("personality_version"),
            "safety_version": config.get("safety_version"),
        },
        "system": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "config": redact_config(dict(config)),
        "provider_health": {
            "groq": check_groq(os.environ.get(config.get("groq_api_key_env", "GROQ_API_KEY"))),
            "ollama": check_ollama(config.get("ollama_base_url", "http://localhost:11434")),
            "piper_model": check_piper(piper_path),
            "piper_package": check_piper_package(),
            "microphone": check_microphone(),
            "audio_output": check_audio_output(),
            "talk_hotkey": check_hotkey(config.get("activation_hotkey")),
            "clip_hotkey": check_hotkey(config.get("clip_hotkey")),
        },
        "paths": {
            "data_dir": str(data_dir),
            "logs_dir": str(logs_dir),
        },
        "logs": _list_recent_logs(logs_dir),
        "memory": _memory_summary(data_dir, include_memories),
    }
    return payload


def export_diagnostics(config: dict[str, Any], include_memories: bool = False) -> Path:
    """Write diagnostics JSON and return the file path."""
    out_dir = get_user_data_dir() / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "kibo_diagnostics.json"
    payload = collect_diagnostics(config, include_memories=include_memories)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def _list_recent_logs(logs_dir: Path) -> list[dict[str, Any]]:
    if not logs_dir.exists():
        return []
    files = sorted(logs_dir.glob("*.log*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "size_bytes": p.stat().st_size} for p in files[:5]]


def _memory_summary(data_dir: Path, include_memories: bool) -> dict[str, Any]:
    memory_dir = data_dir / "vault" / "memories"
    files = sorted(memory_dir.glob("*.md")) if memory_dir.exists() else []
    summary: dict[str, Any] = {"count": len(files)}
    if include_memories:
        summary["files"] = [p.name for p in files]
    return summary
