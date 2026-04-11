"""
ui_manager.py — Transparent frameless always-on-top PySide6 window.

Responsibilities:
  - Render the pet sprite with animated PNG frame sequences
  - Smooth crossfade transitions between animation states
  - One-shot (non-looping) animation support with finished signal
  - Skin-prefix resolution for multi-skin support
  - Display and auto-hide speech bubbles
  - Handle drag-to-move (click anywhere on the pet)
  - Right-click context menu (About, Reset Position, Quit)
  - Receive BrainOutput and update animation + speech bubble accordingly
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QSequentialAnimationGroup,
    QSize, Qt, QTimer, Signal, Slot,
)
from PySide6.QtGui import (
    QAction, QColor, QCursor, QFont, QMouseEvent, QPainter,
    QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QLabel, QMenu, QSizePolicy,
    QVBoxLayout, QWidget,
)

from brain import BrainOutput, PetState

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / "assets" / "animations"
CROSSFADE_MS = 150


class AnimationController:
    """
    Loads PNG frame sequences for each state and cycles them.
    Supports looping and one-shot playback with crossfade transitions.
    """

    def __init__(self, size: QSize, frame_rate_ms: int, skin: str) -> None:
        self._size = size
        self._frame_rate_ms = frame_rate_ms
        self._skin = skin
        self._frames: dict[str, list[QPixmap]] = {}
        self._current_animation: str = "idle"
        self._frame_index: int = 0
        self._loop: bool = True
        self._on_frame_change = None  # callable(QPixmap)
        self._on_animation_finished = None  # callable()

        self._timer = QTimer()
        self._timer.timeout.connect(self._next_frame)

    def set_frame_callback(self, callback) -> None:
        self._on_frame_change = callback

    def set_finished_callback(self, callback) -> None:
        self._on_animation_finished = callback

    def _resolve_animation_path(self, name: str) -> Optional[Path]:
        """Resolve animation name to a directory, checking skin prefix first.

        For 'actions/X' → look for {skin}_action_X/
        For 'intro/X'  → look for {skin}_intro_X/
        For plain name  → look for {skin}_{name}/ then {name}/
        """
        if "/" in name:
            category, clip = name.split("/", 1)
            # category is 'actions' or 'intro' — map to singular form for folder prefix
            folder_prefix = category.rstrip("s")  # actions→action, intro→intro
            skin_dir = ASSETS_DIR / f"{self._skin}_{folder_prefix}_{clip}"
            if skin_dir.exists():
                return skin_dir
            # Fallback: try without skin prefix
            plain_dir = ASSETS_DIR / f"{folder_prefix}_{clip}"
            if plain_dir.exists():
                return plain_dir
            return None

        # Plain animation name (e.g. "idle", "happy")
        skin_dir = ASSETS_DIR / f"{self._skin}_{name}"
        if skin_dir.exists():
            return skin_dir
        plain_dir = ASSETS_DIR / name
        if plain_dir.exists():
            return plain_dir
        return None

    def load_animation(self, name: str) -> bool:
        """Load PNG frames for an animation. Returns True if found."""
        if name in self._frames:
            return True

        state_dir = self._resolve_animation_path(name)
        if state_dir is None or not state_dir.exists():
            logger.warning("Animation dir not found for: %s", name)
            return False

        frames = sorted(state_dir.glob("frame_*.png"))
        if not frames:
            logger.warning("No frames found in: %s", state_dir)
            return False

        pixmaps = []
        for f in frames:
            pm = QPixmap(str(f)).scaled(
                self._size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            pixmaps.append(pm)

        self._frames[name] = pixmaps
        logger.debug("Loaded %d frames for animation '%s' from %s.",
                      len(pixmaps), name, state_dir.name)
        return True

    def preload_all(self) -> None:
        """Preload every state directory found under assets/animations/."""
        if not ASSETS_DIR.exists():
            logger.warning("Assets directory not found: %s", ASSETS_DIR)
            return
        for state_dir in ASSETS_DIR.iterdir():
            if state_dir.is_dir():
                # Use plain folder name for non-skin-prefixed dirs
                self.load_animation(state_dir.name)

    def switch_to(self, name: str, loop: bool = True) -> None:
        if name == self._current_animation and loop == self._loop:
            return
        if name not in self._frames:
            if not self.load_animation(name):
                logger.warning("Falling back to 'idle' — no frames for '%s'.", name)
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
                # One-shot finished — stay on last frame and notify
                if self._on_animation_finished:
                    self._on_animation_finished()
                return

        self._frame_index = next_index
        self._show_current_frame()

    def _show_current_frame(self) -> None:
        frames = self._frames.get(self._current_animation)
        if not frames or self._on_frame_change is None:
            return
        self._on_frame_change(frames[self._frame_index])


class SpeechBubble(QWidget):
    """
    A styled speech bubble widget that auto-hides after a timeout.
    Positioned above the main pet window.
    """

    def __init__(self, timeout_ms: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._timeout_ms = timeout_ms
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label.setFont(QFont("Outfit", 9, QFont.Bold))
        self._label.setStyleSheet("color: #F8F9FA; background: transparent; padding: 4px 6px;")
        self._label.setMaximumWidth(220)

        # Floating drop shadow for modern 3D UI
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 20)
        layout.addWidget(self._label)
        self.setLayout(layout)

    def show_text(self, text: str) -> None:
        if not text:
            self.hide()
            return
        # Truncate very long responses for the bubble
        if len(text) > 200:
            text = text[:197] + "..."
        self._label.setText(text)
        self._label.adjustSize()
        self.adjustSize()
        self.show()
        self._timer.start(self._timeout_ms)

    def append_text(self, chunk: str) -> None:
        current = self._label.text()
        combined = current + chunk
        if len(combined) > 200:
            combined = combined[:197] + "..."
        self._label.setText(combined)
        self._label.adjustSize()
        self.adjustSize()
        # Reset hide timer while streaming
        self._timer.start(self._timeout_ms)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        tail = 12  # tail height
        radius = 12 # Bubble smooth corner radius

        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h - tail, radius, radius)
        # Tail pointing downward at center
        path.moveTo(w / 2 - 10, h - tail)
        path.lineTo(w / 2, h)
        path.lineTo(w / 2 + 10, h - tail)
        path.closeSubpath()

        # Dark Glassmorphism background matching the Kibo premium UI plan
        painter.setBrush(QColor(25, 28, 32, 230))
        # Subtle white outline
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.5))
        painter.drawPath(path)


class UIManager(QWidget):
    """
    Main transparent frameless window containing the pet sprite and speech bubble.
    """

    quit_requested = Signal()
    animation_finished = Signal()

    def __init__(self, config: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._drag_pos: Optional[QPoint] = None
        pet_name = config.get("pet_name", "KIBO")
        skin = config.get("buddy_skin", "skales")

        w, h = config.get("window_size", [200, 200])
        self.setFixedSize(w, h)

        # Window flags
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, not config.get("opaque_fallback", False))
        self.setWindowTitle(pet_name)

        # Sprite label
        self._sprite = QLabel(self)
        self._sprite.setAlignment(Qt.AlignCenter)
        self._sprite.setGeometry(0, 0, w, h)

        # Opacity effect for crossfade
        self._opacity_effect = QGraphicsOpacityEffect(self._sprite)
        self._opacity_effect.setOpacity(1.0)
        self._sprite.setGraphicsEffect(self._opacity_effect)

        # Animation controller
        self._anim = AnimationController(
            size=QSize(w, h),
            frame_rate_ms=config.get("frame_rate_ms", 150),
            skin=skin,
        )
        self._anim.set_frame_callback(self._on_frame)
        self._anim.set_finished_callback(self._on_anim_finished)
        self._anim.preload_all()
        self._anim.switch_to("idle")
        self._anim.start()

        # Crossfade animation group
        self._crossfade_group: Optional[QSequentialAnimationGroup] = None
        self._pending_switch: Optional[tuple[str, bool]] = None

        # Speech bubble (separate window so it floats above pet)
        bubble_timeout = config.get("speech_bubble_timeout_ms", 5000)
        self._bubble = SpeechBubble(timeout_ms=bubble_timeout)
        self._bubble.hide()

        self._streaming_response = ""

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(BrainOutput)
    def on_brain_output(self, output: BrainOutput) -> None:
        anim_name = output.animation_name
        loop = output.loop

        # Crossfade to new animation
        self._crossfade_to(anim_name, loop)

        if output.speech_text and self._config.get("enable_speech_bubbles", True):
            self._streaming_response = ""
            self._bubble.show_text(output.speech_text)
            self._position_bubble()

    @Slot(str)
    def on_response_chunk(self, chunk: str) -> None:
        """Append streaming AI token to the speech bubble."""
        if not self._config.get("enable_speech_bubbles", True):
            return
        if not self._bubble.isVisible():
            self._streaming_response = chunk
            self._bubble.show_text(chunk)
            self._position_bubble()
        else:
            self._bubble.append_text(chunk)

    @Slot(str)
    def on_ai_error(self, message: str) -> None:
        self._bubble.show_text(message)
        self._position_bubble()

    # ------------------------------------------------------------------
    # Crossfade
    # ------------------------------------------------------------------

    def _crossfade_to(self, name: str, loop: bool = True) -> None:
        """Switch animation instantly. Transition fading removed for smoother character logic."""
        current_anim = self._anim._current_animation
        if name == current_anim:
            if loop != self._anim._loop:
                self._anim._loop = loop
            return

        self._anim.switch_to(name, loop)



    # ------------------------------------------------------------------
    # Animation callbacks
    # ------------------------------------------------------------------

    def _on_frame(self, pixmap: QPixmap) -> None:
        self._sprite.setPixmap(pixmap)

    def _on_anim_finished(self) -> None:
        """Called when a one-shot animation completes."""
        self.animation_finished.emit()

    # ------------------------------------------------------------------
    # Bubble positioning
    # ------------------------------------------------------------------

    def _position_bubble(self) -> None:
        pet_pos = self.pos()
        bubble_x = pet_pos.x() + self.width() // 2 - self._bubble.width() // 2
        bubble_y = pet_pos.y() - self._bubble.height() - 5
        # Keep on screen
        screen = QApplication.primaryScreen().geometry()
        bubble_x = max(0, min(bubble_x, screen.width() - self._bubble.width()))
        bubble_y = max(0, bubble_y)
        self._bubble.move(bubble_x, bubble_y)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self._bubble.isVisible():
            self._position_bubble()

    # ------------------------------------------------------------------
    # Drag to move
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: rgba(22, 24, 28, 230);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px;
                padding: 6px;
                font-family: 'Outfit', 'Segoe UI', sans-serif;
                font-weight: 500;
                font-size: 13px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
                margin: 2px 0px;
            }
            QMenu::item:selected {
                background: rgba(144, 238, 144, 40); /* Skales Gecko Green Hover */
                border: 1px solid rgba(144, 238, 144, 80);
                color: #A8F0A8;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 20);
                margin: 4px 8px;
            }
        """)

        pet_name = self._config.get("pet_name", "KIBO")
        about_action = QAction(f"About {pet_name}", self)
        about_action.setEnabled(False)
        menu.addAction(about_action)

        menu.addSeparator()

        reset_action = QAction("Reset Position", self)
        reset_action.triggered.connect(self._reset_position)
        menu.addAction(reset_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_requested)
        menu.addAction(quit_action)

        menu.exec(QCursor.pos())

    def _reset_position(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.width() - 40
        y = screen.height() - self.height() - 80
        self.move(x, y)
        if self._bubble.isVisible():
            self._position_bubble()

    # ------------------------------------------------------------------
    # Startup position
    # ------------------------------------------------------------------

    def place_on_screen(self) -> None:
        """Position pet in bottom-right corner on first show."""
        self._reset_position()

    def closeEvent(self, event) -> None:
        self._anim.stop()
        self._bubble.close()
        super().closeEvent(event)
