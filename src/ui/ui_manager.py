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
    QApplication, QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QLabel, QMenu, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from src.ai.brain import BrainOutput, PetState
from src.core.config_manager import get_bundle_dir
from src.ui.animation_engine import VideoAnimationController

logger = logging.getLogger(__name__)

ASSETS_DIR = get_bundle_dir() / "assets" / "animations"

CROSSFADE_MS = 150


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


class AboutDialog(QWidget):
    """
    A premium dark glass frameless dialog showing information about KIBO.
    """

    def __init__(self, pet_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(320, 200)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header
        header = QLabel(f"About {pet_name}")
        header.setFont(QFont("Outfit", 14, QFont.Bold))
        header.setStyleSheet("color: #FFFFFF;")
        header.setAlignment(Qt.AlignCenter)

        # Version & Details
        details = QLabel(
            "Version 1.1.0\n"
            "An AI-Powered Desktop Companion.\n\n"
            "<a href='https://github.com/yash-dev007/KIBO' style='color: #A8F0A8; text-decoration: none;'>View on GitHub</a>"
        )
        details.setOpenExternalLinks(True)
        details.setFont(QFont("Segoe UI", 10))
        details.setStyleSheet("color: #CCCCCC;")
        details.setAlignment(Qt.AlignCenter)

        # Close button
        btn = QPushButton("Close")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 6px;
                color: #FFFFFF;
                padding: 6px 0;
                font-family: 'Outfit', 'Segoe UI';
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(144, 238, 144, 40);
                border: 1px solid rgba(144, 238, 144, 80);
                color: #A8F0A8;
            }
            QPushButton:pressed {
                background: rgba(144, 238, 144, 20);
            }
        """)
        btn.clicked.connect(self.close)

        layout.addWidget(header)
        layout.addSpacing(10)
        layout.addWidget(details)
        layout.addStretch()
        layout.addWidget(btn)
        self.setLayout(layout)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        painter.setBrush(QColor(22, 24, 28, 240)) # Dark acrylic
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
        painter.drawPath(path)


class UIManager(QWidget):
    """
    Main transparent frameless window containing the pet sprite and speech bubble.
    """

    quit_requested = Signal()
    animation_finished = Signal()
    pet_clicked = Signal()
    show_settings = Signal()

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
        self._anim = VideoAnimationController(
            size=QSize(w, h),
            skin=skin,
            frame_rate_ms=config.get("frame_rate_ms", 150),
        )
        self._anim.frame_ready.connect(self._on_frame)
        self._anim.animation_finished.connect(self._on_anim_finished)
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

    @Slot(dict)
    def on_config_changed(self, new_config: dict) -> None:
        self._config = new_config
        # Some settings like bubble timeout require restarting the bubble
        # or other components. Here we handle what can be updated live.
        self._bubble._timeout_ms = new_config.get("speech_bubble_timeout_ms", 5000)
        self.setAttribute(Qt.WA_TranslucentBackground, not new_config.get("opaque_fallback", False))
        
        # If pet name changed, update window title
        pet_name = new_config.get("pet_name", "KIBO")
        self.setWindowTitle(pet_name)

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
        if event.button() == Qt.LeftButton and self._drag_pos is not None:
            current_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            delta = (current_pos - self._drag_pos).manhattanLength()
            if delta < 5:
                self.pet_clicked.emit()
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
        
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.show_settings.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        reset_action = QAction("Reset Position", self)
        reset_action.triggered.connect(self._reset_position)
        menu.addAction(reset_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_requested)
        menu.addAction(quit_action)

        menu.exec(QCursor.pos())

    @Slot()
    def reset_position(self) -> None:
        """Public slot — resets pet to bottom-right corner."""
        self._reset_position()

    @Slot(str)
    def show_notification(self, message: str) -> None:
        """Public slot — displays a proactive notification in the speech bubble."""
        self._bubble.show_text(message)
        self._position_bubble()

    @Slot()
    def show_about(self) -> None:
        """Public slot — opens the About dialog."""
        self._show_about_dialog()

    def _reset_position(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.width() - 40
        y = screen.height() - self.height() - 80
        self.move(x, y)
        if self._bubble.isVisible():
            self._position_bubble()

    def _show_about_dialog(self) -> None:
        if not hasattr(self, "_about_dialog") or self._about_dialog is None:
            pet_name = self._config.get("pet_name", "KIBO")
            self._about_dialog = AboutDialog(pet_name, self)
        
        # Center the dialog on the screen
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self._about_dialog.width()) // 2
        y = (screen.height() - self._about_dialog.height()) // 2
        self._about_dialog.move(x, y)
        self._about_dialog.show()

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
