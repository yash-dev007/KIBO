from pathlib import Path

from src.ui import animation_engine
from src.ui.animation_engine import VideoAnimationController


def test_generic_idle_resolves_first_skin_idle_clip(tmp_path, monkeypatch):
    idle_dir = tmp_path / "bubbles" / "idle"
    idle_dir.mkdir(parents=True)
    expected = idle_dir / "chill.webm"
    expected.write_bytes(b"")
    (idle_dir / "vibe.webm").write_bytes(b"")
    monkeypatch.setattr(animation_engine, "ASSETS_DIR", tmp_path)

    controller = VideoAnimationController.__new__(VideoAnimationController)
    controller._skin = "bubbles"

    assert controller._resolve_webm("idle") == expected
