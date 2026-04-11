import json
import logging
import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot, QPoint
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QGraphicsDropShadowEffect, QApplication
)

from config_manager import get_user_data_dir

logger = logging.getLogger(__name__)


class MessageBubble(QWidget):
    def __init__(self, role: str, content: str, timestamp: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.role = role
        self.content = content
        self.timestamp = timestamp

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        self.label = QLabel(self.content)
        self.label.setWordWrap(True)
        self.label.setFont(QFont("Outfit", 10))
        self.label.setStyleSheet("color: white;")
        layout.addWidget(self.label)

        time_label = QLabel(self.timestamp)
        time_label.setFont(QFont("Outfit", 7))
        time_label.setStyleSheet("color: #888888;")
        time_label.setAlignment(Qt.AlignRight if role == "user" else Qt.AlignLeft)
        layout.addWidget(time_label)

    def append_chunk(self, chunk: str) -> None:
        self.content += chunk
        self.label.setText(self.content)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 8, 8)

        if self.role == "user":
            painter.setBrush(QColor(0, 255, 136, 30))
            painter.setPen(Qt.NoPen)
        else:
            painter.setBrush(QColor(255, 255, 255, 10))
            painter.setPen(Qt.NoPen)

        painter.drawPath(path)


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
        title_label.setStyleSheet("color: white;")
        layout.addWidget(title_label)

        desc_label = QLabel(task.get("description", ""))
        desc_label.setWordWrap(True)
        desc_label.setFont(QFont("Outfit", 9))
        desc_label.setStyleSheet("color: #CCCCCC;")
        layout.addWidget(desc_label)

        btn_layout = QHBoxLayout()
        self.approve_btn = QPushButton("Run")
        self.approve_btn.setCursor(Qt.PointingHandCursor)
        self.approve_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 255, 136, 40);
                color: white;
                border: 1px solid rgba(0, 255, 136, 100);
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: rgba(0, 255, 136, 80); }
        """)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 100, 100, 40);
                color: white;
                border: 1px solid rgba(255, 100, 100, 100);
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: rgba(255, 100, 100, 80); }
        """)
        
        btn_layout.addWidget(self.approve_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 8, 8)

        painter.setBrush(QColor(255, 200, 0, 20)) # yellowish tint
        painter.setPen(QPen(QColor(255, 200, 0, 60), 1.0))
        painter.drawPath(path)


class ChatWindow(QWidget):
    message_sent = Signal(str)
    closed = Signal()
    task_approved = Signal(str)
    task_cancelled = Signal(str)

    def __init__(self, config: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(380, 520)
        self._config = config
        self._drag_pos: Optional[QPoint] = None

        self._history_dir = get_user_data_dir() / "conversations"
        self._history_dir.mkdir(parents=True, exist_ok=True)

        self._init_ui()
        
        self._current_ai_bubble: Optional[MessageBubble] = None
        self._session_history = []
        
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
        
        container = QWidget()
        l = QHBoxLayout(container)
        l.setContentsMargins(0,0,0,0)
        l.addStretch()
        l.addWidget(widget)
        l.addStretch()
        
        self.scroll_layout.addWidget(container)
        self._scroll_to_bottom()
        
        if not self.isVisible():
            self.show()
        
    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(40)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 0, 10, 0)
        
        title = QLabel("● KIBO")
        title.setFont(QFont("Outfit", 11, QFont.Bold))
        title.setStyleSheet("color: white;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                border: none;
                font-weight: bold;
            }
            QPushButton:hover { color: white; }
        """)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

        # Scroll area for messages
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 30);
                border-radius: 3px;
            }
        """)
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)

        # Input bar
        input_bar = QWidget()
        input_bar.setFixedHeight(52)
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(10, 0, 10, 10)

        mic_btn = QPushButton("🎤")
        mic_btn.setFixedSize(32, 32)
        mic_btn.setCursor(Qt.PointingHandCursor)
        mic_btn.setStyleSheet("background: rgba(255,255,255,10); color: white; border-radius: 16px;")
        # Wiring to voice listener is handled outside or handled via hotkey
        input_layout.addWidget(mic_btn)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask KIBO anything...")
        self.input_field.setFont(QFont("Outfit", 10))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 10);
                color: white;
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 16px;
                padding: 0 12px;
            }
            QLineEdit:focus { border: 1px solid rgba(0, 255, 136, 100); }
        """)
        self.input_field.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.input_field)

        send_btn = QPushButton("→")
        send_btn.setFixedSize(32, 32)
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.setStyleSheet("background: rgba(0, 255, 136, 40); color: white; border-radius: 16px;")
        send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(send_btn)

        layout.addWidget(header)
        layout.addWidget(self.scroll_area)
        layout.addWidget(input_bar)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        painter.setBrush(QColor(22, 24, 28, 240)) # dark acrylic
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
        painter.drawPath(path)

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

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.load_history()
            self.show()
            self.input_field.setFocus()

    def _scroll_to_bottom(self) -> None:
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _get_timestamp(self) -> str:
        return datetime.datetime.now().strftime("%H:%M")

    def _send_message(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()
        
        # Add User Bubble
        bubble = MessageBubble("user", text, self._get_timestamp(), self)
        
        # Layout alignment hack for bubbles
        container = QWidget()
        l = QHBoxLayout(container)
        l.setContentsMargins(0,0,0,0)
        l.addStretch()
        l.addWidget(bubble)
        self.scroll_layout.addWidget(container)
        
        self.message_sent.emit(text)
        
        # Prepare AI Bubble
        self._current_ai_bubble = MessageBubble("assistant", "", self._get_timestamp(), self)
        container_ai = QWidget()
        la = QHBoxLayout(container_ai)
        la.setContentsMargins(0,0,0,0)
        la.addWidget(self._current_ai_bubble)
        la.addStretch()
        self.scroll_layout.addWidget(container_ai)
        
        self._scroll_to_bottom()
        
        # Save to history
        self._append_to_history("user", text)

    @Slot(str)
    def on_chunk(self, chunk: str) -> None:
        if self._current_ai_bubble:
            self._current_ai_bubble.append_chunk(chunk)
            self._scroll_to_bottom()

    @Slot(str)
    def on_response_done(self, text: str) -> None:
        if self._current_ai_bubble:
            if not self._current_ai_bubble.content:
                self._current_ai_bubble.append_chunk(text)
            self._append_to_history("assistant", self._current_ai_bubble.content)
            self._current_ai_bubble = None
        self._scroll_to_bottom()

    @Slot(str)
    def on_error(self, msg: str) -> None:
        if self._current_ai_bubble:
            self._current_ai_bubble.append_chunk(f"\n[Error: {msg}]")
            self._current_ai_bubble.setStyleSheet("color: #ff6b6b;")
            self._current_ai_bubble = None
        self._scroll_to_bottom()

    def _get_history_file(self) -> Path:
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        return self._history_dir / f"{date_str}.json"

    def _append_to_history(self, role: str, content: str) -> None:
        file = self._get_history_file()
        history = []
        if file.exists():
            try:
                history = json.loads(file.read_text("utf-8"))
            except Exception:
                pass
        
        history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.datetime.now().isoformat()
        })
        
        file.write_text(json.dumps(history, indent=2), "utf-8")

    def load_history(self) -> None:
        file = self._get_history_file()
        if not file.exists():
            return
            
        # Clear current bubbles
        for i in reversed(range(self.scroll_layout.count())): 
            widget_to_remove = self.scroll_layout.itemAt(i).widget()
            self.scroll_layout.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)

        try:
            history = json.loads(file.read_text("utf-8"))
            for msg in history[-50:]:
                role = msg.get("role")
                content = msg.get("content", "")
                ts = msg.get("timestamp", "")
                try:
                    dt = datetime.datetime.fromisoformat(ts)
                    time_str = dt.strftime("%H:%M")
                except Exception:
                    time_str = self._get_timestamp()
                    
                bubble = MessageBubble(role, content, time_str, self)
                container = QWidget()
                l = QHBoxLayout(container)
                l.setContentsMargins(0,0,0,0)
                if role == "user":
                    l.addStretch()
                    l.addWidget(bubble)
                else:
                    l.addWidget(bubble)
                    l.addStretch()
                self.scroll_layout.addWidget(container)
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            
        self._scroll_to_bottom()

    def hideEvent(self, event) -> None:
        self.closed.emit()
        super().hideEvent(event)
