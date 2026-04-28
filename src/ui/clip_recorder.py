"""
clip_recorder.py — Ring-buffer clip recorder for KIBO.

Taps into the animation frame stream (via on_frame slot) and maintains a
rolling deque of the last 5 seconds. On dump(), encodes them as an
animated WebP to ~/.kibo/clips/ and copies the file path to the clipboard.

Requires: Pillow >= 10.0.0
"""
from __future__ import annotations

import io
import logging
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QBuffer, QIODevice, QObject, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

_CLIPS_DIR = Path.home() / ".kibo" / "clips"
_FPS = 30
_DURATION_S = 5
_MAX_FRAMES = _FPS * _DURATION_S


class ClipRecorder(QObject):
    """Records animation frames into a ring buffer and encodes on demand."""

    clip_saved = Signal(str)   # path to the saved clip
    clip_error = Signal(str)   # human-readable error message

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._frames: deque[QPixmap] = deque(maxlen=_MAX_FRAMES)
        self._encoding = False

    @Slot(QPixmap)
    def on_frame(self, pixmap: QPixmap) -> None:
        """Append a copy of each rendered frame to the ring buffer."""
        self._frames.append(pixmap.copy())

    @Slot()
    def dump(self) -> None:
        """Snapshot the ring buffer and encode to animated WebP in background."""
        if self._encoding:
            logger.debug("Clip encoding already in progress, skipping.")
            return

        frames = list(self._frames)
        if len(frames) < 2:
            self.clip_error.emit("Not enough frames captured yet — keep KIBO visible a moment longer.")
            return

        # Convert QPixmaps → PNG bytes on the main thread (Qt GUI requirement)
        frame_bytes: list[bytes] = []
        for pixmap in frames:
            buf = QBuffer()
            buf.open(QIODevice.WriteOnly)
            pixmap.save(buf, "PNG")
            frame_bytes.append(bytes(buf.data()))

        self._encoding = True
        threading.Thread(
            target=self._encode_and_save,
            args=(frame_bytes,),
            daemon=True,
        ).start()

    def _encode_and_save(self, frame_bytes: list[bytes]) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.clip_error.emit("Pillow not installed. Run: pip install Pillow>=10.0.0")
            self._encoding = False
            return

        try:
            pil_frames = [Image.open(io.BytesIO(b)).convert("RGBA") for b in frame_bytes]

            _CLIPS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = _CLIPS_DIR / f"kibo_clip_{timestamp}.webp"

            duration_ms = 1000 // _FPS
            pil_frames[0].save(
                out_path,
                save_all=True,
                append_images=pil_frames[1:],
                duration=duration_ms,
                loop=0,
                format="WEBP",
            )
            logger.info("Clip saved: %s", out_path)
            self.clip_saved.emit(str(out_path))
        except Exception as exc:
            logger.exception("Clip encoding failed")
            self.clip_error.emit(f"Clip save failed: {exc}")
        finally:
            self._encoding = False
