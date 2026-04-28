"""
preprocess_alpha.py — Bake VP9 alpha into WebM assets (one-time, offline).

KIBO's animation engine requires WebM files with native VP9 alpha (yuva420p)
so it can skip the software chroma-key pass entirely. Run this script once
after adding or updating animation assets.

Usage:
    python scripts/preprocess_alpha.py

Requirements:
    ffmpeg must be on PATH (https://ffmpeg.org/download.html).

What it does:
    For every *.webm under assets/animations/ that does NOT already have an
    alpha channel, runs:
        ffmpeg -i input.webm \
               -vf colorkey=0x00ff00:0.1:0.05 \
               -c:v libvpx-vp9 -pix_fmt yuva420p \
               -b:v 0 -crf 33 \
               input.webm  (in-place via a temp file)

    The colorkey filter treats pure green (0x00ff00) as background.
    Adjust the similarity (0.1) and blend (0.05) values if edges look rough.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent / "assets" / "animations"
GREEN = "0x00ff00"
SIMILARITY = "0.1"
BLEND = "0.05"


def has_alpha(path: Path) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_streams", "-select_streams", "v:0",
         str(path)],
        capture_output=True, text=True,
    )
    return "yuva420p" in result.stdout


def convert(path: Path) -> None:
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False, dir=path.parent) as tmp:
        tmp_path = Path(tmp.name)

    skin_name = path.parent.parent.name
    bg_color = "0x0000ff" if skin_name == "skales" else "0x00ff00"

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(path),
                "-vf", f"colorkey={bg_color}:{SIMILARITY}:{BLEND}",
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                "-b:v", "0", "-crf", "33",
                str(tmp_path),
            ],
            check=True,
        )
        shutil.move(str(tmp_path), str(path))
        print(f"  ✓ {path.relative_to(ASSETS_DIR.parent.parent)}")
    except subprocess.CalledProcessError as exc:
        tmp_path.unlink(missing_ok=True)
        print(f"  ✗ {path.name}: ffmpeg error {exc.returncode}", file=sys.stderr)


def main() -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH. Install from https://ffmpeg.org/download.html")

    webms = sorted(ASSETS_DIR.rglob("*.webm"))
    if not webms:
        print("No .webm files found under", ASSETS_DIR)
        return

    print(f"Found {len(webms)} WebM file(s). Checking for native alpha...")
    needs_convert = [p for p in webms if not has_alpha(p)]

    if not needs_convert:
        print("All assets already have native VP9 alpha. Nothing to do.")
        return

    print(f"{len(needs_convert)} file(s) need conversion:")
    for p in needs_convert:
        convert(p)

    print("\nDone. Re-run KIBO to use the updated assets.")


if __name__ == "__main__":
    main()
