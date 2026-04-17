"""
animation_engine.py — High-performance animation controllers for KIBO.

Two controllers are provided:
  • PngAnimationController  — cycles pre-loaded PNG frame sequences via QTimer.
  • VideoAnimationController — plays WebM videos via QMediaPlayer + QVideoSink,
    with automatic PNG fallback if no .webm file is found.

Video Frame Pipeline (optimised):
  1. QVideoFrame arrives from the media decoder.
  2. Convert → QImage, downscale to widget size FIRST (huge pixel reduction).
  3. Fast-path: if the decoder already delivered an alpha channel, skip numpy.
  4. Slow-path: chroma-key the background colour away with soft-edge anti-alias
     and colour despill, all on the tiny downscaled image.

The WMF backend (set via QT_MEDIA_BACKEND=windows in main.py) natively decodes
VP9 alpha, so the fast-path fires almost every frame on Windows 10/11 with the
Web Media Extensions codec pack installed.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame, QVideoSink

from src.core.config_manager import get_bundle_dir

# ── Try Rust native chroma-key, fall back to numpy ──────────────────────
try:
    import kibo_core
    _HAS_RUST_CK = True
except ImportError:
    _HAS_RUST_CK = False

logger = logging.getLogger(__name__)

if _HAS_RUST_CK:
    logger.info("Rust chroma-key loaded (kibo_core) — native performance")
else:
    logger.info("Rust chroma-key not available — using numpy fallback")

ASSETS_DIR = get_bundle_dir() / "assets" / "animations"

# ── Chroma-key constants ────────────────────────────────────────────────
# Pixels whose max-channel distance from the background is below CORE are
# fully transparent.  Between CORE and EDGE they fade linearly.
# Tighter thresholds protect lighter features (eyes, highlights) from
# being eaten by the chroma-key.
_CK_CORE_THRESHOLD = 40
_CK_EDGE_THRESHOLD = 85


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

        # 1. Downscale FIRST — drastically reduces pixel count for any
        #    subsequent processing (from ~500k+ pixels to ~40k).
        image = image.scaled(
            self._size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )

        # 2. Ensure ARGB32 for alpha support
        image = image.convertToFormat(QImage.Format.Format_ARGB32)

        # 3. Probe native alpha on the first frame of each clip
        if self._has_native_alpha is None:
            self._has_native_alpha = self._probe_alpha(image)
            if self._has_native_alpha:
                logger.debug("Native VP9 alpha detected — chroma-key disabled")

        # 4. Fast path — decoder already gave us transparency
        if self._has_native_alpha:
            self.frame_ready.emit(QPixmap.fromImage(image))
            return

        # 5. Slow path — software chroma-key
        pixmap = self._chroma_key(image)
        self.frame_ready.emit(pixmap)

    # ── Alpha probe ─────────────────────────────────────────────────────

    @staticmethod
    def _probe_alpha(image: QImage) -> bool:
        """Return True if the image already contains non-opaque pixels.

        Samples corners, edge midpoints, and a center patch to avoid
        false negatives from videos with near-opaque borders.
        """
        w, h = image.width(), image.height()
        arr = np.frombuffer(image.bits(), np.uint8).reshape((h, w, 4))

        # Sample corners (5×5 patches)
        s = 5
        patches = [
            arr[:s, :s, 3],         # top-left
            arr[:s, -s:, 3],        # top-right
            arr[-s:, :s, 3],        # bottom-left
            arr[-s:, -s:, 3],       # bottom-right
            arr[:s, w//2-s:w//2+s, 3],  # top-center
            arr[-s:, w//2-s:w//2+s, 3], # bottom-center
        ]
        border = np.concatenate([p.ravel() for p in patches])
        return bool(np.any(border < 250))

    # ── Software chroma-key ─────────────────────────────────────────────

    @staticmethod
    def _chroma_key(image: QImage) -> QPixmap:
        """Remove solid-colour background with soft edges and despill."""
        w, h = image.width(), image.height()

        if _HAS_RUST_CK:
            # ── Rust fast path — kibo_core.chroma_key ──────────────────
            ptr = image.bits()
            raw = bytes(ptr)
            keyed_bytes = kibo_core.chroma_key(
                raw, w, h, _CK_CORE_THRESHOLD, _CK_EDGE_THRESHOLD
            )
            keyed = QImage(keyed_bytes, w, h, w * 4, QImage.Format.Format_ARGB32).copy()
            return QPixmap.fromImage(keyed)

        # ── Numpy fallback ──────────────────────────────────────────────
        ptr = image.bits()
        arr = np.frombuffer(ptr, np.uint8).reshape((h, w, 4)).copy()

        bg = arr[0, 0, :3].astype(np.int16)
        diff = np.abs(arr[:, :, :3].astype(np.int16) - bg)
        max_diff = np.max(diff, axis=-1)

        # Core background → fully transparent
        arr[max_diff < _CK_CORE_THRESHOLD, 3] = 0

        # Fringe → soft alpha edge + colour despill
        fringe = (max_diff >= _CK_CORE_THRESHOLD) & (max_diff < _CK_EDGE_THRESHOLD)
        if np.any(fringe):
            span = float(_CK_EDGE_THRESHOLD - _CK_CORE_THRESHOLD)
            alpha = (max_diff[fringe] - _CK_CORE_THRESHOLD) / span
            arr[fringe, 3] = (arr[fringe, 3].astype(np.float32) * alpha).astype(np.uint8)

            # Despill: clamp the dominant background channel
            dom = int(np.argmax(bg))
            others = [i for i in range(3) if i != dom]
            avg = (arr[fringe, others[0]].astype(np.uint16)
                   + arr[fringe, others[1]].astype(np.uint16)) // 2
            arr[fringe, dom] = np.minimum(arr[fringe, dom], avg)

        keyed = QImage(arr.tobytes(), w, h, QImage.Format.Format_ARGB32).copy()
        return QPixmap.fromImage(keyed)

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
            self._using_png = True
            self._png.switch_to(self._current_animation, self._loop)
            self._png.start()

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        """Emit animation_finished for one-shot clips when the video truly ends."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia and not self._loop:
            self.animation_finished.emit()
