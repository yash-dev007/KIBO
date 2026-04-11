"""
download_assets.py — Download Skales mascot WebM files and convert to PNG sequences.

Prerequisites:
    - ffmpeg on PATH (install via: winget install ffmpeg)
    - httpx installed (already in requirements.txt)

Usage:
    python download_assets.py              # Download skales skin only
    python download_assets.py --skin capy  # Download capybara skin
    python download_assets.py --skin all   # Download all skins
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx is required. Install via: pip install httpx")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent
ASSETS_DIR = PROJECT_ROOT / "assets"
WEBM_DIR = ASSETS_DIR / "webm"
ANIM_DIR = ASSETS_DIR / "animations"

BASE_URL = "https://raw.githubusercontent.com/skalesapp/skales/main/apps/web/public/mascot"

# ── Asset manifest ──────────────────────────────────────────────────────────

SKINS: dict[str, dict[str, list[str]]] = {
    "skales": {
        "idle": ["stand", "still", "stillstand"],
        "action": [
            "breathing", "bubblegum", "dumbell", "fly", "screentap",
            "sleep", "smartphone", "sneeze", "spinning", "stamp",
            "stepcheck", "stillstamp", "stretch", "sunglasses", "tired",
        ],
        "intro": ["elevator", "intro", "paper", "spawn"],
    },
    "capy": {
        "idle": ["stand", "still", "stillstand"],
        "action": [
            "breathing", "bubblegum", "dumbell", "fly", "screentap",
            "sleep", "smartphone", "sneeze", "spinning", "stamp",
            "stepcheck", "stillstamp", "stretch", "sunglasses", "tired",
        ],
        "intro": ["elevator", "intro", "paper", "spawn"],
    },
}

IMG_SIZE = 200
FPS = 60


# ── Helpers ─────────────────────────────────────────────────────────────────

def check_ffmpeg() -> bool:
    """Return True if ffmpeg is found."""
    local_ffmpeg = PROJECT_ROOT / "ffmpeg.exe"
    if local_ffmpeg.exists():
        return True
    return shutil.which("ffmpeg") is not None


def download_file(url: str, dest: Path) -> bool:
    """Download a file. Skip if already exists. Returns True on success."""
    if dest.exists():
        logger.info("  ⏭  Already exists: %s", dest.name)
        return True

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("  ⬇  Downloading %s ...", dest.name)

    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        return True
    except Exception as exc:
        logger.error("  ✗  Failed to download %s: %s", url, exc)
        return False


def convert_webm_to_png(webm_path: Path, output_dir: Path) -> bool:
    """Convert a WebM file to a PNG frame sequence using ffmpeg."""
    if output_dir.exists() and any(output_dir.glob("frame_*.png")):
        logger.info("  ⏭  Frames already exist: %s", output_dir.name)
        return True

    output_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = str(output_dir / "frame_%04d.png")

    vf = (
        f"fps={FPS},"
        f"scale={IMG_SIZE}:{IMG_SIZE}:"
        f"force_original_aspect_ratio=decrease,"
        f"pad={IMG_SIZE}:{IMG_SIZE}:(ow-iw)/2:(oh-ih)/2:color=black@0,"
        f"format=rgba"
    )

    local_ffmpeg = PROJECT_ROOT / "ffmpeg.exe"
    ffmpeg_cmd = str(local_ffmpeg) if local_ffmpeg.exists() else "ffmpeg"

    cmd = [
        ffmpeg_cmd, "-y",
        "-vcodec", "libvpx-vp9",
        "-i", str(webm_path),
        "-vf", vf,
        output_pattern,
    ]

    logger.info("  🔄 Converting → %s", output_dir.name)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            logger.error("  ✗  ffmpeg error:\n%s", result.stderr[-500:])
            return False

        frame_count = len(list(output_dir.glob("frame_*.png")))
        logger.info("  ✓  %d frames extracted.", frame_count)
        return True
    except subprocess.TimeoutExpired:
        logger.error("  ✗  ffmpeg timed out for %s", webm_path.name)
        return False
    except FileNotFoundError:
        logger.error("  ✗  ffmpeg not found on PATH.")
        return False


# ── Main pipeline ───────────────────────────────────────────────────────────

def process_skin(skin: str) -> None:
    """Download and convert all assets for a single skin."""
    manifest = SKINS.get(skin)
    if not manifest:
        logger.error("Unknown skin '%s'. Available: %s", skin, list(SKINS.keys()))
        return

    logger.info("═" * 60)
    logger.info("Processing skin: %s", skin)
    logger.info("═" * 60)

    for category, clips in manifest.items():
        logger.info("\n── %s/%s (%d clips) ──", skin, category, len(clips))

        for clip_name in clips:
            url = f"{BASE_URL}/{skin}/{category}/{clip_name}.webm"
            webm_dest = WEBM_DIR / skin / category / f"{clip_name}.webm"

            if not download_file(url, webm_dest):
                continue

            # Output folder: {skin}_{category}_{clip_name} for actions/intro variants
            # For idle: {skin}_idle_{variant}
            output_folder_name = f"{skin}_{category}_{clip_name}"
            output_dir = ANIM_DIR / output_folder_name

            convert_webm_to_png(webm_dest, output_dir)

    logger.info("\n✅ Skin '%s' complete.", skin)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Skales mascot assets for KIBO.")
    parser.add_argument(
        "--skin", default="skales", choices=["skales", "capy", "all"],
        help="Which skin to download (default: skales)",
    )
    args = parser.parse_args()

    if not check_ffmpeg():
        logger.error("ffmpeg.exe not found in project root and not on PATH.")
        sys.exit(1)

    skins_to_process = list(SKINS.keys()) if args.skin == "all" else [args.skin]

    for skin in skins_to_process:
        process_skin(skin)

    logger.info("\n" + "═" * 60)
    logger.info("All done! Run KIBO with: python main.py")
    logger.info("═" * 60)


if __name__ == "__main__":
    main()
