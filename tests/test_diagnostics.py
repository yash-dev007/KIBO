from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.system.diagnostics import collect_diagnostics, export_diagnostics, redact_config


def test_redact_config_removes_secrets_and_prompt() -> None:
    cfg = {
        "groq_api_key_env": "GROQ_API_KEY",
        "google_token": "secret-token",
        "system_prompt": "private prompt",
        "pet_name": "KIBO",
    }
    redacted = redact_config(cfg)
    assert redacted["groq_api_key_env"] == "<redacted>"
    assert redacted["google_token"] == "<redacted>"
    assert redacted["system_prompt"] == "<redacted>"
    assert redacted["pet_name"] == "KIBO"


def test_collect_diagnostics_excludes_memory_contents_by_default(tmp_path: Path) -> None:
    memory_dir = tmp_path / "vault" / "memories"
    memory_dir.mkdir(parents=True)
    (memory_dir / "memory.md").write_text("User likes private espresso.", encoding="utf-8")

    with patch("src.system.diagnostics.get_user_data_dir", return_value=tmp_path), \
         patch("src.system.diagnostics.check_ollama", return_value={"available": False, "reason": "offline"}), \
         patch("src.system.diagnostics.check_microphone", return_value={"available": False, "reason": "no mic"}), \
         patch("src.system.diagnostics.check_audio_output", return_value={"available": False, "reason": "no output"}), \
         patch("src.system.diagnostics.check_piper_package", return_value={"available": False, "reason": "no piper"}):
        payload = collect_diagnostics({"system_prompt": "private"}, include_memories=False)

    assert payload["memory"] == {"count": 1}
    assert "User likes private espresso" not in json.dumps(payload)


def test_export_diagnostics_writes_json(tmp_path: Path) -> None:
    with patch("src.system.diagnostics.get_user_data_dir", return_value=tmp_path), \
         patch("src.system.diagnostics.check_ollama", return_value={"available": False, "reason": "offline"}), \
         patch("src.system.diagnostics.check_microphone", return_value={"available": False, "reason": "no mic"}), \
         patch("src.system.diagnostics.check_audio_output", return_value={"available": False, "reason": "no output"}), \
         patch("src.system.diagnostics.check_piper_package", return_value={"available": False, "reason": "no piper"}):
        path = export_diagnostics({"pet_name": "KIBO"})

    assert path == tmp_path / "diagnostics" / "kibo_diagnostics.json"
    assert json.loads(path.read_text(encoding="utf-8"))["app"]["name"] == "KIBO"
