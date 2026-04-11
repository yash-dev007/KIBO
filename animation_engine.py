import logging
from pathlib import Path
from typing import Optional, Dict, List
import numpy as np

from PySide6.QtCore import QObject, Signal, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink, QVideoFrame

from config_manager import get_bundle_dir

logger = logging.getLogger(__name__)

ASSETS_DIR = get_bundle_dir() / "assets" / "animations"

class PngAnimationController(QObject):
    """
    Loads PNG frame sequences for each state and cycles them.
    Supports looping and one-shot playback.
    """
    frame_ready = Signal(QPixmap)
    animation_finished = Signal()

    def __init__(self, size: QSize, frame_rate_ms: int, skin: str) -> None:
        super().__init__()
        self._size = size
        self._frame_rate_ms = frame_rate_ms
        self._skin = skin
        self._frames: Dict[str, List[QPixmap]] = {}
        self._current_animation: str = "idle"
        self._frame_index: int = 0
        self._loop: bool = True

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)

    def _resolve_animation_path(self, name: str) -> Optional[Path]:
        if "/" in name:
            category, clip = name.split("/", 1)
            folder_prefix = category.rstrip("s")
            skin_dir = ASSETS_DIR / f"{self._skin}_{folder_prefix}_{clip}"
            if skin_dir.exists():
                return skin_dir
            plain_dir = ASSETS_DIR / f"{folder_prefix}_{clip}"
            if plain_dir.exists():
                return plain_dir
            return None

        skin_dir = ASSETS_DIR / f"{self._skin}_{name}"
        if skin_dir.exists():
            return skin_dir
        plain_dir = ASSETS_DIR / name
        if plain_dir.exists():
            return plain_dir
        return None

    def load_animation(self, name: str) -> bool:
        if name in self._frames:
            return True

        state_dir = self._resolve_animation_path(name)
        if state_dir is None or not state_dir.exists():
            return False

        frames = sorted(state_dir.glob("frame_*.png"))
        if not frames:
            return False

        pixmaps = []
        for f in frames:
            pm = QPixmap(str(f)).scaled(
                self._size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            pixmaps.append(pm)

        self._frames[name] = pixmaps
        return True

    def preload_all(self) -> None:
        if not ASSETS_DIR.exists():
            return
        for state_dir in ASSETS_DIR.iterdir():
            if state_dir.is_dir():
                self.load_animation(state_dir.name)

    def switch_to(self, name: str, loop: bool = True) -> None:
        if name == self._current_animation and loop == self._loop:
            return
        if name not in self._frames:
            if not self.load_animation(name):
                name = "idle"
                if name not in self._frames:
                    return

        self._current_animation = name
        self._frame_index = 0
        self._loop = loop
        self._show_current_frame()

    def start(self) -> None:
        self._timer.start(self._frame_rate_ms)

    def stop(self) -> None:
        self._timer.stop()

    def _next_frame(self) -> None:
        frames = self._frames.get(self._current_animation)
        if not frames:
            return

        next_index = self._frame_index + 1

        if next_index >= len(frames):
            if self._loop:
                next_index = 0
            else:
                self.animation_finished.emit()
                return

        self._frame_index = next_index
        self._show_current_frame()

    def _show_current_frame(self) -> None:
        frames = self._frames.get(self._current_animation)
        if not frames:
            return
        self.frame_ready.emit(frames[self._frame_index])


class VideoAnimationController(QObject):
    animation_finished = Signal()
    frame_ready = Signal(QPixmap)

    def __init__(self, size: QSize, skin: str, frame_rate_ms: int = 150) -> None:
        super().__init__()
        self._size = size
        self._skin = skin
        self._loop = True
        self._current_animation = ""
        
        self._player = QMediaPlayer(self)
        self._sink = QVideoSink(self)
        self._player.setVideoOutput(self._sink)
        
        self._sink.videoFrameChanged.connect(self._on_video_frame_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        
        # Fallback PNG controller
        self._png_fallback = PngAnimationController(size, frame_rate_ms, skin)
        self._png_fallback.frame_ready.connect(self.frame_ready.emit)
        self._png_fallback.animation_finished.connect(self.animation_finished.emit)
        self._using_fallback = False

    def _resolve_webm_path(self, name: str) -> Optional[Path]:
        """Resolve WebM file path (e.g. idle/stand or intro/spawn)."""
        # Name might be 'idle', or 'intro/spawn'
        if "/" in name:
            category, clip = name.split("/", 1)
        else:
            category = "idle"
            clip = name

        webm_path = ASSETS_DIR / self._skin / category / f"{clip}.webm"
        if webm_path.exists():
            return webm_path
        
        # Try without skin folder if generic
        generic_path = ASSETS_DIR / category / f"{clip}.webm"
        if generic_path.exists():
            return generic_path
            
        return None

    def switch_to(self, name: str, loop: bool = True) -> None:
        if name == self._current_animation and loop == self._loop and self._player.playbackState() == QMediaPlayer.PlayingState:
            return
            
        self._current_animation = name
        self._loop = loop
        
        webm_path = self._resolve_webm_path(name)
        if webm_path:
            self._using_fallback = False
            self._png_fallback.stop()
            
            self._player.setSource(QUrl.fromLocalFile(str(webm_path)))
            self._player.play()
        else:
            # Fallback to PNG
            self._using_fallback = True
            self._player.stop()
            self._png_fallback.switch_to(name, loop)

    def start(self) -> None:
        if self._using_fallback:
            self._png_fallback.start()
        else:
            if self._player.playbackState() != QMediaPlayer.PlayingState:
                self._player.play()

    def stop(self) -> None:
        self._player.stop()
        self._png_fallback.stop()

    def _on_video_frame_changed(self, frame: QVideoFrame) -> None:
        if not frame.isValid():
            return
            
        # Convert QVideoFrame to a QImage with transparency support
        image = frame.toImage()
        if not image.isNull():
            # Force to ARGB32 to allow transparency manipulation
            image = image.convertToFormat(QImage.Format.Format_ARGB32)
            
            # --- Chroma Keying using Numpy ---
            # We assume the background color is at (0,0). 
            # If the image has no alpha, we set all matching pixels to transparent.
            
            width, height = image.width(), image.height()
            ptr = image.bits()
            # Wrap image bits in a numpy array (B, G, R, A order for ARGB32)
            arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))
            
            # Get background color from top-left pixel (RGB only)
            bg_color = arr[0, 0, :3].copy()
            
            # Mask pixels that are close to the background color (tolerance = 40)
            diff = np.abs(arr[:, :, :3].astype(np.int16) - bg_color.astype(np.int16))
            mask = np.all(diff < 40, axis=-1)
            
            # Set alpha channel to 0 for background pixels
            # Note: arr is a view into image.bits(), so this modifies the QImage directly!
            arr[mask, 3] = 0
            
            # Create pixmap from the modified image
            pixmap = QPixmap.fromImage(image).scaled(
                self._size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.frame_ready.emit(pixmap)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.StoppedState:
            if self._loop:
                self._player.setPosition(0)
                self._player.play()
            else:
                self.animation_finished.emit()

