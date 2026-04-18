import logging
import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot, QPoint, QTimer
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QGraphicsDropShadowEffect, QApplication,
    QSizePolicy, QSpacerItem,
)

from src.core.config_manager import get_user_data_dir

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MessageBubble — a single chat message with rounded background
# ---------------------------------------------------------------------------

class MessageBubble(QWidget):
    """A single chat bubble (user or assistant) with word-wrapped text."""

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.is_loading = (role == "assistant" and not content)
        self._loading_dots = 1

        # --- Size policies ---
        # Horizontal: prefer up to max, vertical: grow to fit content
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        # --- Internal layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 8)
        layout.setSpacing(3)

        # Message text
        self.label = QLabel("." if self.is_loading else self.content)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.label.setFont(QFont("Outfit", 10))
        self.label.setStyleSheet("color: #E0E0E0; background: transparent;")
        self.label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout.addWidget(self.label)

        # Timestamp
        time_label = QLabel(self.timestamp)
        time_label.setFont(QFont("Outfit", 7))
        time_label.setStyleSheet("color: #888888; background: transparent;")
        time_label.setAlignment(Qt.AlignRight if role == "user" else Qt.AlignLeft)
        layout.addWidget(time_label)

        # Loading dots animation
        if self.is_loading:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._animate_loading)
            self._timer.start(400)

    # -- Loading animation --------------------------------------------------

    def _animate_loading(self) -> None:
        self._loading_dots = (self._loading_dots % 3) + 1
        self.label.setText("·" * self._loading_dots)

    # -- Streaming chunks ---------------------------------------------------

    def append_chunk(self, chunk: str) -> None:
        if self.is_loading:
            self.is_loading = False
            if hasattr(self, "_timer"):
                self._timer.stop()
            self.content = ""

        self.content += chunk
        self.label.setText(self.content)
        # Force geometry recalculation so the scroll area can resize
        self.label.updateGeometry()
        self.updateGeometry()

    # -- Custom paint (rounded rect background) -----------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        r = 14.0
        w, h = float(self.width()), float(self.height())
        path.addRoundedRect(0.0, 0.0, w, h, r, r)

        if self.role == "user":
            painter.setBrush(QColor(50, 50, 50, 180))
            painter.setPen(QPen(QColor(80, 80, 80, 100), 1.0))
        else:
            painter.setBrush(QColor(25, 25, 25, 200))
            painter.setPen(QPen(QColor(60, 60, 60, 100), 1.0))

        painter.drawPath(path)


# ---------------------------------------------------------------------------
# ApprovalWidget — task approval prompt
# ---------------------------------------------------------------------------

class ApprovalWidget(QWidget):
    def __init__(self, task: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.task_id = task["id"]
        self.approved = False
        self.resolved = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        title_label = QLabel(f"Task Approval: {task.get('title', 'Unknown Task')}")
        title_label.setWordWrap(True)
        title_label.setFont(QFont("Outfit", 10, QFont.Bold))
        title_label.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(title_label)

        desc_label = QLabel(task.get("description", ""))
        desc_label.setWordWrap(True)
        desc_label.setFont(QFont("Outfit", 9))
        desc_label.setStyleSheet("color: #A0A0A0;")
        layout.addWidget(desc_label)

        btn_layout = QHBoxLayout()
        self.approve_btn = QPushButton("Run")
        self.approve_btn.setCursor(Qt.PointingHandCursor)
        self.approve_btn.setStyleSheet("""
            QPushButton {
                background: rgba(143, 191, 106, 40);
                color: #D4EDB8;
                border: 1px solid rgba(143, 191, 106, 100);
                border-radius: 6px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: rgba(143, 191, 106, 80); }
        """)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(200, 90, 70, 40);
                color: #F0C0B0;
                border: 1px solid rgba(200, 90, 70, 100);
                border-radius: 6px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: rgba(200, 90, 70, 80); }
        """)

        btn_layout.addWidget(self.approve_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 8, 8)

        painter.setBrush(QColor(40, 40, 40, 150))
        painter.setPen(QPen(QColor(80, 80, 80, 150), 1.0))
        painter.drawPath(path)


# ---------------------------------------------------------------------------
# ChatWindow — the main frameless chat panel
# ---------------------------------------------------------------------------

class ChatWindow(QWidget):
    message_sent = Signal(str)
    closed = Signal()
    visibility_changed = Signal(bool)
    task_approved = Signal(str)
    task_cancelled = Signal(str)
    mic_pressed = Signal()

    def __init__(self, config: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(380, 520)
        self._config = config
        self._drag_pos: Optional[QPoint] = None

        self._current_ai_bubble: Optional[MessageBubble] = None
        self._current_user_bubble: Optional[MessageBubble] = None
        self._mic_cooldown = False
        self._auto_scroll = True

        self._init_ui()

    # ------------------------------------------------------------------
    # Approval prompt
    # ------------------------------------------------------------------

    @Slot(dict)
    def show_approval_prompt(self, task: dict) -> None:
        widget = ApprovalWidget(task, self)

        def on_approve():
            if not widget.resolved:
                widget.resolved = True
                widget.approve_btn.setEnabled(False)
                widget.cancel_btn.setEnabled(False)
                widget.approve_btn.setText("Approved")
                self.task_approved.emit(task["id"])

        def on_cancel():
            if not widget.resolved:
                widget.resolved = True
                widget.approve_btn.setEnabled(False)
                widget.cancel_btn.setEnabled(False)
                widget.cancel_btn.setText("Cancelled")
                self.task_cancelled.emit(task["id"])

        widget.approve_btn.clicked.connect(on_approve)
        widget.cancel_btn.clicked.connect(on_cancel)

        container = self._make_row(widget, center=True)
        self.scroll_layout.addWidget(container)
        self._scroll_to_bottom()

        if not self.isVisible():
            self.show()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 12, 0)

        dot = QLabel("●")
        dot.setFont(QFont("Outfit", 8))
        dot.setStyleSheet("color: #8FBF6A;")
        hl.addWidget(dot)

        title = QLabel(self._config.get("pet_name", "KIBO"))
        title.setFont(QFont("Outfit", 12, QFont.Bold))
        title.setStyleSheet("color: #FFFFFF; letter-spacing: 1px;")
        hl.addWidget(title)

        hl.addSpacing(8)

        model_name = self._config.get("ollama_model", "llama3.2").split(":")[0]
        model_pill = QLabel(model_name)
        model_pill.setFont(QFont("Outfit", 8))
        model_pill.setStyleSheet("color: #888888; background: transparent;")
        hl.addWidget(model_pill)

        hl.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(40, 40, 40, 150);
                color: #888888;
                border: 1px solid rgba(80, 80, 80, 150);
                border-radius: 13px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background: rgba(200, 70, 70, 150);
                color: #FFFFFF;
                border-color: rgba(250, 100, 100, 200);
            }
        """)
        close_btn.clicked.connect(self.hide)
        hl.addWidget(close_btn)

        # ── Scroll area ──────────────────────────────────────────────
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QWidget#scroll_inner { background: transparent; }
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(80, 80, 80, 100);
                border-radius: 2px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(120, 120, 120, 150);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }
        """)

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("scroll_inner")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(6, 8, 6, 8)
        self.scroll_layout.setSpacing(6)

        # Top spacer pushes messages to the bottom (like a real chat)
        self._top_spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.scroll_layout.addItem(self._top_spacer)

        self.scroll_area.setWidget(self.scroll_content)

        # Auto-scroll when content grows
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self._on_scroll_range_changed)

        # ── Input bar ─────────────────────────────────────────────────
        input_bar = QWidget()
        input_bar.setFixedHeight(58)
        input_bar.setStyleSheet("background: transparent;")
        il = QHBoxLayout(input_bar)
        il.setContentsMargins(12, 0, 12, 12)
        il.setSpacing(8)

        mic_btn = QPushButton("●")  # Minimalist record circle
        mic_btn.setFixedSize(34, 34)
        mic_btn.setCursor(Qt.PointingHandCursor)
        mic_btn.setFont(QFont("Outfit", 12))
        mic_btn.setStyleSheet("""
            QPushButton {
                background: rgba(40, 40, 40, 100);
                color: #888888;
                border: 1px solid rgba(80, 80, 80, 100);
                border-radius: 17px;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background: rgba(60, 60, 60, 150);
                color: #E0E0E0;
                border-color: rgba(100, 100, 100, 150);
            }
        """)
        mic_btn.clicked.connect(self._on_mic_clicked)
        mic_btn.setToolTip("Hold to speak (or press Ctrl+K)")
        il.addWidget(mic_btn)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Say anything to KIBO…")
        self.input_field.setFont(QFont("Outfit", 10))
        self.input_field.setFixedHeight(34)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: rgba(20, 20, 20, 160);
                color: #E0E0E0;
                border: 1px solid rgba(80, 80, 80, 100);
                border-radius: 17px;
                padding: 0 14px;
                selection-background-color: rgba(100, 100, 100, 100);
            }
            QLineEdit:focus {
                border: 1px solid rgba(120, 120, 120, 150);
                background: rgba(30, 30, 30, 200);
            }
        """)
        self.input_field.returnPressed.connect(self._send_message)
        il.addWidget(self.input_field)

        send_btn = QPushButton("▲")  # Modern UP triangle
        send_btn.setFixedSize(34, 34)
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.setFont(QFont("Outfit", 10))
        send_btn.setStyleSheet("""
            QPushButton {
                background: rgba(60, 60, 60, 150);
                color: #E0E0E0;
                border: 1px solid rgba(100, 100, 100, 150);
                border-radius: 17px;
                padding-bottom: 1px;
            }
            QPushButton:hover {
                background: rgba(80, 80, 80, 200);
                border-color: rgba(120, 120, 120, 200);
            }
            QPushButton:pressed { background: rgba(40, 40, 40, 150); }
        """)
        send_btn.clicked.connect(self._send_message)
        il.addWidget(send_btn)

        # ── Assemble ──────────────────────────────────────────────────
        root.addWidget(header)
        root.addWidget(self.scroll_area, 1)  # stretch=1 so it fills space
        root.addWidget(input_bar)

    # ------------------------------------------------------------------
    # Background paint (dark chocolate glass)
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 14, 14)

        painter.setBrush(QColor(10, 10, 10, 245))
        painter.setPen(QPen(QColor(60, 60, 60, 100), 1.0))
        painter.drawPath(path)

        highlight = QPainterPath()
        highlight.moveTo(14, 0)
        highlight.lineTo(self.width() - 14, 0)
        painter.setPen(QPen(QColor(80, 80, 80, 80), 1.0))
        painter.drawPath(highlight)

    # ------------------------------------------------------------------
    # Drag-to-move (header region only)
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and event.position().y() <= 40:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None

    # ------------------------------------------------------------------
    # Mic cooldown
    # ------------------------------------------------------------------

    @Slot()
    def _on_mic_clicked(self) -> None:
        if self._mic_cooldown:
            return
        self._mic_cooldown = True
        self.mic_pressed.emit()
        QTimer.singleShot(2000, self._reset_mic_cooldown)

    def _reset_mic_cooldown(self) -> None:
        self._mic_cooldown = False

    # ------------------------------------------------------------------
    # Toggle visibility
    # ------------------------------------------------------------------

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.input_field.setFocus()

    # ------------------------------------------------------------------
    # Scrolling helpers
    # ------------------------------------------------------------------

    def _scroll_to_bottom(self) -> None:
        """Immediate scroll to bottom."""
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_scroll_range_changed(self, _min: int, _max: int) -> None:
        """Auto-scroll whenever the scroll range grows (new content added)."""
        if self._auto_scroll:
            self.scroll_area.verticalScrollBar().setValue(_max)

    # ------------------------------------------------------------------
    # Bubble row factory
    # ------------------------------------------------------------------

    def _make_row(self, widget: QWidget, role: str = "", center: bool = False) -> QWidget:
        """
        Wrap *widget* in a full-width container with an HBoxLayout that
        pushes the bubble to the correct side.  This avoids passing
        Qt.AlignRight/Left to addWidget which breaks word-wrap sizing.
        """
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        h = QHBoxLayout(container)
        h.setContentsMargins(4, 0, 4, 0)
        h.setSpacing(0)

        if center:
            h.addStretch()
            h.addWidget(widget)
            h.addStretch()
        elif role == "user":
            h.addStretch()
            h.addWidget(widget)
        else:
            h.addWidget(widget)
            h.addStretch()

        return container

    # ------------------------------------------------------------------
    # Timestamp
    # ------------------------------------------------------------------

    def _get_timestamp(self) -> str:
        return datetime.datetime.now().strftime("%H:%M")

    # ------------------------------------------------------------------
    # Send message
    # ------------------------------------------------------------------

    def _send_message(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()
        self._auto_scroll = True

        # Finalize any in-flight AI bubble
        if self._current_ai_bubble is not None:
            if not self._current_ai_bubble.content:
                self._current_ai_bubble.label.setText("…")
            if hasattr(self._current_ai_bubble, "_timer"):
                self._current_ai_bubble._timer.stop()
            self._current_ai_bubble = None

        # User bubble
        user_bubble = MessageBubble("user", text, self._get_timestamp(), self)
        self.scroll_layout.addWidget(self._make_row(user_bubble, "user"))

        self.message_sent.emit(text)

        # AI loading bubble
        self._current_ai_bubble = MessageBubble("assistant", "", self._get_timestamp(), self)
        self.scroll_layout.addWidget(self._make_row(self._current_ai_bubble, "assistant"))

    # ------------------------------------------------------------------
    # Voice visual feedback slots
    # ------------------------------------------------------------------
    
    @Slot()
    def show_listening_indicator(self) -> None:
        self._auto_scroll = True
        
        # Stop any existing AI bubble
        if self._current_ai_bubble is not None:
            if not self._current_ai_bubble.content:
                self._current_ai_bubble.label.setText("…")
            if hasattr(self._current_ai_bubble, "_timer"):
                self._current_ai_bubble._timer.stop()
            self._current_ai_bubble = None
            
        self._current_user_bubble = MessageBubble("user", "[Listening...]", self._get_timestamp(), self)
        self.scroll_layout.addWidget(self._make_row(self._current_user_bubble, "user"))
        self._scroll_to_bottom()

    @Slot(str)
    def update_voice_transcript(self, text: str) -> None:
        if self._current_user_bubble is not None:
            self._current_user_bubble.content = text
            self._current_user_bubble.label.setText(text)
            self._current_user_bubble.label.updateGeometry()
            self._current_user_bubble.updateGeometry()
            self._current_user_bubble = None
        else:
            user_bubble = MessageBubble("user", text, self._get_timestamp(), self)
            self.scroll_layout.addWidget(self._make_row(user_bubble, "user"))

        # AI loading bubble now that text is transcribed
        self._current_ai_bubble = MessageBubble("assistant", "", self._get_timestamp(), self)
        self.scroll_layout.addWidget(self._make_row(self._current_ai_bubble, "assistant"))
        self._scroll_to_bottom()

    @Slot(str)
    def cancel_listening(self, error_msg: str) -> None:
        if self._current_user_bubble is not None:
            self._current_user_bubble.content = f"[{error_msg}]"
            self._current_user_bubble.label.setText(self._current_user_bubble.content)
            self._current_user_bubble = None

    # ------------------------------------------------------------------
    # AI streaming slots
    # ------------------------------------------------------------------

    @Slot(str)
    def on_chunk(self, chunk: str) -> None:
        if self._current_ai_bubble:
            self._current_ai_bubble.append_chunk(chunk)

    @Slot(str)
    def on_response_done(self, text: str) -> None:
        if self._current_ai_bubble:
            self._current_ai_bubble.content = text
            self._current_ai_bubble.label.setText(text)
            self._current_ai_bubble.label.updateGeometry()
            self._current_ai_bubble.updateGeometry()
            self._current_ai_bubble = None

    @Slot(str)
    def on_error(self, msg: str) -> None:
        if self._current_ai_bubble:
            self._current_ai_bubble.append_chunk(f"\n[Error: {msg}]")
            self._current_ai_bubble = None

    # ------------------------------------------------------------------
    # History persistence
    # ------------------------------------------------------------------

    def _clear_messages(self) -> None:
        """Remove all message bubbles from the scroll area."""
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(1)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()
        self._current_ai_bubble = None
        self._current_user_bubble = None

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.visibility_changed.emit(True)
        self.input_field.setFocus()

    def hideEvent(self, event) -> None:
        self._clear_messages()
        self.visibility_changed.emit(False)
        self.closed.emit()
        super().hideEvent(event)
