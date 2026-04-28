"""
animation_engine.py — Animation controllers for KIBO.

Two controllers are provided:
  • PngAnimationController  — cycles pre-loaded PNG frame sequences via QTimer.
  • VideoAnimationController — plays WebM videos via QMediaPlayer + QVideoSink,
    with automatic PNG fallback if no .webm file is found or the asset lacks
    native VP9 alpha.

Video Frame Pipeline:
  1. QVideoFrame arrives from the media decoder (WMF backend, set in main.py).
  2. Convert → QImage, downscale to widget size FIRST (huge pixel reduction).
  3. Probe native alpha on the first frame of each clip.
  4. If native alpha present → emit pixmap directly (zero CPU chroma-key).
  5. If no native alpha → log a warning and switch to PNG fallback.
     Run scripts/preprocess_alpha.py to bake transparency into WebM assets.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame, QVideoSink

from src.core.config_manager import get_bundle_dir

logger = logging.getLogger(__name__)

ASSETS_DIR = get_bundle_dir() / "assets" / "animations"


# ═══════════════════════════════════════════════════════════════════════
# PNG Animation Controller
# ═══════════════════════════════════════════════════════════════════════

class PngAnimationController(QObject):
    """Cycles pre-loaded PNG frame sequences. Supports looping and one-shot."""

    frame_ready = Signal(QPixmap)
    animation_finished = Signal()

    def __init__(self, size: QSize, frame_rate_ms: int, skin: str) -> None:
        super().__init__()
        self._size = size
        self._frame_rate_ms = frame_rate_ms
        self._skin = skin
        self._frames: dict[str, list[QPixmap]] = {}
        self._current: str = "idle"
        self._index: int = 0
        self._loop: bool = True

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

    # ── Asset resolution ────────────────────────────────────────────────

    def _resolve_path(self, name: str) -> Optional[Path]:
        """Try <skin>/<category>/<clip>/ then <category>/<clip>/."""
        if "/" in name:
            category, clip = name.split("/", 1)
        else:
            category, clip = name, name

        for base in (ASSETS_DIR / self._skin, ASSETS_DIR):
            candidate = base / category / clip
            if candidate.is_dir():
                return candidate
        # Legacy flat layout: <skin>_<name>/
        for base in (ASSETS_DIR,):
            for prefix in (f"{self._skin}_{name}", name):
                candidate = base / prefix
                if candidate.is_dir():
                    return candidate
        return None

    # ── Loading ─────────────────────────────────────────────────────────

    def load(self, name: str) -> bool:
        if name in self._frames:
            return True
        folder = self._resolve_path(name)
        if folder is None:
            return False
        pngs = sorted(folder.glob("frame_*.png"))
        if not pngs:
            return False
        self._frames[name] = [
            QPixmap(str(p)).scaled(self._size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            for p in pngs
        ]
        return True

    def preload_all(self) -> None:
        if not ASSETS_DIR.exists():
            return
        for d in ASSETS_DIR.iterdir():
            if d.is_dir():
                self.load(d.name)

    # ── Playback control ────────────────────────────────────────────────

    def switch_to(self, name: str, loop: bool = True) -> None:
        if name == self._current and loop == self._loop:
            return
        if name not in self._frames and not self.load(name):
            name = "idle"
            if name not in self._frames:
                return
        self._current = name
        self._index = 0
        self._loop = loop
        self._emit_current()

    def start(self) -> None:
        self._timer.start(self._frame_rate_ms)

    def stop(self) -> None:
        self._timer.stop()

    # ── Internal ────────────────────────────────────────────────────────

    def _advance(self) -> None:
        frames = self._frames.get(self._current)
        if not frames:
            return
        nxt = self._index + 1
        if nxt >= len(frames):
            if self._loop:
                nxt = 0
            else:
                self.animation_finished.emit()
                return
        self._index = nxt
        self._emit_current()

    def _emit_current(self) -> None:
        frames = self._frames.get(self._current)
        if frames:
            self.frame_ready.emit(frames[self._index])


# ═══════════════════════════════════════════════════════════════════════
# Video Animation Controller
# ═══════════════════════════════════════════════════════════════════════

class VideoAnimationController(QObject):
    """Plays WebM videos with native alpha or chroma-key fallback."""

    frame_ready = Signal(QPixmap)
    animation_finished = Signal()

    def __init__(self, size: QSize, skin: str, frame_rate_ms: int = 150) -> None:
        super().__init__()
        self._size = size
        self._skin = skin
        self._loop = True
        self._current_animation = ""

        # Media pipeline
        self._player = QMediaPlayer(self)
        self._sink = QVideoSink(self)
        self._player.setVideoOutput(self._sink)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._switching = False  # True while setSource+play is in-flight; gates PNG fallback

        # PNG fallback
        self._png = PngAnimationController(size, frame_rate_ms, skin)
        self._png.frame_ready.connect(self.frame_ready.emit)
        self._png.animation_finished.connect(self.animation_finished.emit)
        self._using_png = False

        # Track whether the decoder provides alpha so we can skip chroma-key
        self._has_native_alpha: Optional[bool] = None

    # ── WebM path resolution ────────────────────────────────────────────

    def _resolve_webm(self, name: str) -> Optional[Path]:
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
        if (name == self._current_animation and loop == self._loop
                and self._player.playbackState() == QMediaPlayer.PlayingState):
            return

        self._current_animation = name
        self._loop = loop
        self._has_native_alpha = None  # re-probe on new clip

        webm = self._resolve_webm(name)
        if webm:
            self._using_png = False
            self._png.stop()
            self._switching = True  # suppress PNG fallback until PlayingState fires
            self._player.setLoops(QMediaPlayer.Infinite if loop else 1)
            self._player.setSource(QUrl.fromLocalFile(str(webm)))
            self._player.play()
        else:
            self._using_png = True
            self._player.stop()
            self._png.switch_to(name, loop)
            self._png.start()

    def start(self) -> None:
        if self._using_png:
            self._png.start()
        elif self._player.playbackState() != QMediaPlayer.PlayingState:
            self._player.play()

    def stop(self) -> None:
        self._player.stop()
        self._png.stop()

    # ── Per-frame processing ────────────────────────────────────────────

    def _on_frame(self, frame: QVideoFrame) -> None:
        if not frame.isValid():
            return

        image = frame.toImage()
        if image.isNull():
            return

        # Downscale first — drastically reduces pixel count (~500k → ~40k)
        image = image.scaled(self._size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        image = image.convertToFormat(QImage.Format.Format_ARGB32)

        if self._has_native_alpha is None:
            self._has_native_alpha = self._probe_alpha(image)
            if self._has_native_alpha:
                logger.debug("Native VP9 alpha detected for '%s'", self._current_animation)
            else:
                logger.warning(
                    "WebM '%s' has no native alpha channel — falling back to PNG. "
                    "Run scripts/preprocess_alpha.py to bake transparency into assets.",
                    self._current_animation,
                )
                self._switch_to_png_fallback()
                return

        if self._has_native_alpha:
            self.frame_ready.emit(QPixmap.fromImage(image))

    # ── Alpha probe (pure Qt, no numpy) ────────────────────────────────

    @staticmethod
    def _probe_alpha(image: QImage) -> bool:
        """Return True if the image already contains non-opaque pixels.

        Samples 6 border points to detect native VP9 alpha without numpy.
        """
        w, h = image.width(), image.height()
        sample_points = [
            (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
            (w // 2, 0), (w // 2, h - 1),
        ]
        return any(QColor(image.pixel(x, y)).alpha() < 250 for x, y in sample_points)

    def _switch_to_png_fallback(self) -> None:
        self._using_png = True
        self._player.stop()
        self._png.switch_to(self._current_animation, self._loop)
        self._png.start()

    # ── Playback state ──────────────────────────────────────────────────

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlayingState:
            self._switching = False  # new clip is actually playing — safe to handle errors again
            return
        if state != QMediaPlayer.StoppedState:
            return
        if self._switching:
            return  # stop was caused by setSource during a switch; not an error

        # Unexpected stop (not natural EndOfMedia) → decoder error, fall back to PNG
        if self._player.mediaStatus() != QMediaPlayer.MediaStatus.EndOfMedia:
            logger.warning(
                "Video stopped unexpectedly (status=%s), falling back to PNG",
                self._player.mediaStatus(),
            )
            self._switch_to_png_fallback()

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        """Emit animation_finished for one-shot clips when the video truly ends."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia and not self._loop:
            self.animation_finished.emit()
