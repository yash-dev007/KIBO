"""
animation_engine.py — WebM-only animation controller for KIBO.

VideoAnimationController plays WebM clips via QMediaPlayer + QVideoSink.

Frame Pipeline:
  1. QVideoFrame arrives from the media decoder (WMF backend, set in main.py).
  2. Convert → QImage, downscale to widget size.
  3. Probe native alpha on first frame of each clip.
  4. If native alpha present  → emit pixmap directly (zero CPU work).
  5. If no native alpha       → apply numpy chroma-key (remove green screen)
                                then emit pixmap.

There is NO PNG fallback. All animation assets must be .webm files.
To bake alpha into green-screen WebMs in advance, run:
    python scripts/preprocess_alpha.py   (requires ffmpeg on PATH)
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame, QVideoSink

from src.core.config_manager import get_bundle_dir

logger = logging.getLogger(__name__)

ASSETS_DIR = get_bundle_dir() / "assets" / "animations"


class VideoAnimationController(QObject):
    """Plays WebM videos with native alpha or on-the-fly chroma-key."""

    frame_ready = Signal(QPixmap)
    animation_finished = Signal()

    # Green-screen removal thresholds (match preprocess_alpha.py defaults)
    _CHROMA_SIMILARITY = 0.35
    _CHROMA_BLEND = 0.10

    def __init__(self, size: QSize, skin: str, frame_rate_ms: int = 150) -> None:
        super().__init__()
        self._size = size
        self._skin = skin
        self._loop = True
        self._current_animation = ""
        self._has_native_alpha: Optional[bool] = None

        self._player = QMediaPlayer(self)
        self._sink = QVideoSink(self)
        self._player.setVideoOutput(self._sink)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

    # ── WebM path resolution ────────────────────────────────────────────

    def _resolve_webm(self, name: str) -> Optional[Path]:
        """Resolve category/clip → .webm path under skin or root."""
        if "/" in name:
            category, clip = name.split("/", 1)
        else:
            category, clip = "idle", name

        for base in (ASSETS_DIR / self._skin, ASSETS_DIR):
            path = base / category / f"{clip}.webm"
            if path.is_file():
                return path
        return None

    # ── Playback control ────────────────────────────────────────────────

    def switch_to(self, name: str, loop: bool = True) -> None:
        if (
            name == self._current_animation
            and loop == self._loop
            and self._player.playbackState() == QMediaPlayer.PlayingState
        ):
            return

        self._current_animation = name
        self._loop = loop
        self._has_native_alpha = None  # re-probe on new clip

        webm = self._resolve_webm(name)
        if webm:
            self._player.setLoops(QMediaPlayer.Infinite if loop else 1)
            self._player.setSource(QUrl.fromLocalFile(str(webm)))
            self._player.play()
        else:
            logger.warning(
                "No WebM found for animation '%s' (skin=%s). "
                "Ensure assets/animations/%s/%s/<clip>.webm exists.",
                name, self._skin, self._skin, name.split("/")[0],
            )

    def start(self) -> None:
        if self._player.playbackState() != QMediaPlayer.PlayingState:
            self._player.play()

    def stop(self) -> None:
        self._player.stop()

    # ── Per-frame processing ────────────────────────────────────────────

    def _on_frame(self, frame: QVideoFrame) -> None:
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return

        # Downscale first — drastically reduces per-pixel work
        image = image.scaled(self._size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        image = image.convertToFormat(QImage.Format.Format_ARGB32)

        # Probe once per clip
        if self._has_native_alpha is None:
            self._has_native_alpha = self._probe_alpha(image)
            if self._has_native_alpha:
                logger.debug("Native VP9 alpha detected for '%s'", self._current_animation)
            else:
                logger.debug(
                    "No native alpha for '%s' — applying software chroma-key.",
                    self._current_animation,
                )

        if not self._has_native_alpha:
            image = self._chroma_key(image)

        self.frame_ready.emit(QPixmap.fromImage(image))

    # ── Alpha probe ────────────────────────────────────────────────────

    @staticmethod
    def _probe_alpha(image: QImage) -> bool:
        """Return True if the image already contains non-opaque pixels."""
        w, h = image.width(), image.height()
        sample_points = [
            (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
            (w // 2, 0), (w // 2, h - 1),
        ]
        return any(QColor(image.pixel(x, y)).alpha() < 250 for x, y in sample_points)

    # ── Software chroma-key ────────────────────────────────────────────

    def _chroma_key(self, image: QImage) -> QImage:
        """Remove chroma-key background via numpy vectorised chroma-key.

        Dynamically samples the top-left pixel to determine the background color.
        """
        try:
            import numpy as np

            ptr = image.bits()
            # ARGB32 on little-endian x86: bytes in memory are B, G, R, A
            arr = (
                np.frombuffer(ptr, dtype=np.uint8)
                .copy()
                .reshape((image.height(), image.width(), 4))
            )

            # Sample top-left pixel as the background color
            bg_b = arr[0, 0, 0].astype(np.float32) / 255.0
            bg_g = arr[0, 0, 1].astype(np.float32) / 255.0
            bg_r = arr[0, 0, 2].astype(np.float32) / 255.0

            b = arr[:, :, 0].astype(np.float32) / 255.0
            g = arr[:, :, 1].astype(np.float32) / 255.0
            r = arr[:, :, 2].astype(np.float32) / 255.0

            dist = np.sqrt((r - bg_r) ** 2 + (g - bg_g) ** 2 + (b - bg_b) ** 2)

            # Ramp: fully transparent within similarity, fully opaque after +blend
            alpha = np.clip(
                (dist - self._CHROMA_SIMILARITY) / self._CHROMA_BLEND, 0.0, 1.0
            )
            arr[:, :, 3] = (alpha * 255).astype(np.uint8)

            result = QImage(
                arr.tobytes(), image.width(), image.height(),
                QImage.Format_ARGB32,
            )
            return result.copy()  # detach from the numpy buffer lifetime

        except ImportError:
            logger.warning(
                "numpy not available — chroma-key skipped, character may show solid "
                "background. Install numpy or run scripts/preprocess_alpha.py."
            )
            return image

    # ── Media status ────────────────────────────────────────────────────

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        """Emit animation_finished for one-shot clips when the video ends."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia and not self._loop:
            self.animation_finished.emit()
