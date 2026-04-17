import json
import logging
import types
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QFormLayout, QCheckBox, QComboBox, QSpinBox, QSlider, QPlainTextEdit,
    QGraphicsDropShadowEffect, QMessageBox
)

from src.core.config_manager import get_app_root

logger = logging.getLogger(__name__)

class SettingsWindow(QWidget):
    settings_changed = Signal(dict)
    closed = Signal()
    clear_memory_requested = Signal()

    def __init__(self, config: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(480, 600)
        self._original_config = config
        self._current_config = dict(config)
        self._drag_pos: Optional[QPoint] = None

        self._init_ui()
        self._populate_fields()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(40)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 0, 10, 0)
        
        title = QLabel("Settings")
        title.setFont(QFont("Outfit", 12, QFont.Bold))
        title.setStyleSheet("color: white;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888888;
                border: none;
                font-weight: bold;
                border-radius: 12px;
            }
            QPushButton:hover { 
                color: #FFFFFF; 
                background: rgba(200, 70, 70, 150); 
            }
        """)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

        # Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: transparent; }
            QTabBar::tab {
                background: rgba(40, 40, 40, 150);
                color: #888888;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: rgba(60, 60, 60, 150);
                color: #E0E0E0;
                font-weight: bold;
            }
            QWidget { color: #E0E0E0; font-family: 'Outfit'; }
            QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {
                background: rgba(20, 20, 20, 160);
                border: 1px solid rgba(80, 80, 80, 100);
                border-radius: 4px;
                color: #E0E0E0;
                padding: 4px;
            }
            QCheckBox { spacing: 8px; }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                background: rgba(20, 20, 20, 160);
                border: 1px solid rgba(80, 80, 80, 100);
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background: rgba(80, 80, 80, 200);
            }
        """)

        self._init_general_tab()
        self._init_ai_tab()
        self._init_notifications_tab()
        self._init_appearance_tab()

        layout.addWidget(header)
        layout.addWidget(self.tabs)

        # Footer
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(15, 10, 15, 15)
        
        self.restart_warning = QLabel("Some changes require a restart.")
        self.restart_warning.setStyleSheet("color: #ffcc00;")
        self.restart_warning.hide()
        footer_layout.addWidget(self.restart_warning)
        
        footer_layout.addStretch()

        save_btn = QPushButton("Save")
        save_btn.setFixedSize(80, 32)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background: rgba(60, 60, 60, 150);
                border: 1px solid rgba(100, 100, 100, 150);
                border-radius: 6px;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover { background: rgba(80, 80, 80, 200); }
        """)
        save_btn.clicked.connect(self._save_settings)
        footer_layout.addWidget(save_btn)

        layout.addWidget(footer)

    def _init_general_tab(self) -> None:
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.f_pet_name = QLineEdit()
        layout.addRow("Pet Name:", self.f_pet_name)
        
        self.f_buddy_skin = QComboBox()
        self.f_buddy_skin.addItems(["skales"])
        layout.addRow("Buddy Skin:", self.f_buddy_skin)
        
        self.f_hotkey = QLineEdit()
        layout.addRow("Activation Hotkey:", self.f_hotkey)

        self.tabs.addTab(tab, "General")

    def _init_ai_tab(self) -> None:
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.f_ai_enabled = QCheckBox("Enable AI")
        layout.addRow("", self.f_ai_enabled)

        self.f_memory_enabled = QCheckBox("Enable Smart Memory")
        layout.addRow("", self.f_memory_enabled)
        
        self.btn_clear_memory = QPushButton("Clear Memory")
        self.btn_clear_memory.setCursor(Qt.PointingHandCursor)
        self.btn_clear_memory.setStyleSheet("""
            QPushButton {
                background: rgba(150, 40, 40, 100);
                border: 1px solid rgba(200, 50, 50, 100);
                border-radius: 4px;
                color: white;
                padding: 4px 8px;
            }
            QPushButton:hover { background: rgba(200, 50, 50, 150); }
        """)
        self.btn_clear_memory.clicked.connect(self._on_clear_memory)
        layout.addRow("", self.btn_clear_memory)
        
        self.f_ollama_url = QLineEdit()
        layout.addRow("Ollama Base URL:", self.f_ollama_url)
        
        self.f_model = QLineEdit()
        layout.addRow("Ollama Model:", self.f_model)
        
        self.f_system_prompt = QPlainTextEdit()
        layout.addRow("System Prompt:", self.f_system_prompt)

        self.tabs.addTab(tab, "AI")
        
    def _on_clear_memory(self) -> None:
        reply = QMessageBox.question(self, 'Clear Memory', 'Are you sure you want to delete all KIBO memories?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.clear_memory_requested.emit()
            QMessageBox.information(self, 'Cleared', 'All memories have been cleared.')

    def _init_notifications_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.f_proactive_enabled = QCheckBox("Enable Proactive Notifications")
        layout.addWidget(self.f_proactive_enabled)
        
        form = QFormLayout()
        self.f_quiet_start = QSpinBox()
        self.f_quiet_start.setRange(0, 23)
        form.addRow("Quiet Hours Start:", self.f_quiet_start)
        
        self.f_quiet_end = QSpinBox()
        self.f_quiet_end.setRange(0, 23)
        form.addRow("Quiet Hours End:", self.f_quiet_end)
        layout.addLayout(form)
        
        layout.addWidget(QLabel("Notification Types:"))
        self.f_types = {}
        for nt in ["morning-greeting", "idle-checkin", "eod-summary", "cpu-panic", 
                   "battery-low", "meeting-reminder", "email-alert", "task-blocked"]:
            cb = QCheckBox(nt)
            self.f_types[nt] = cb
            layout.addWidget(cb)
            
        layout.addStretch()
        self.tabs.addTab(tab, "Notifications")

    def _init_appearance_tab(self) -> None:
        tab = QWidget()
        layout = QFormLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.f_window_size = QSlider(Qt.Horizontal)
        self.f_window_size.setRange(150, 300)
        layout.addRow("Window Size (px):", self.f_window_size)
        
        self.f_frame_rate = QSpinBox()
        self.f_frame_rate.setRange(10, 1000)
        layout.addRow("Frame Rate (ms):", self.f_frame_rate)
        
        self.f_bubble_timeout = QSpinBox()
        self.f_bubble_timeout.setRange(1000, 30000)
        self.f_bubble_timeout.setSingleStep(1000)
        layout.addRow("Bubble Timeout (ms):", self.f_bubble_timeout)
        
        self.f_opaque = QCheckBox("Use Opaque Background Fallback")
        layout.addRow("", self.f_opaque)

        self.tabs.addTab(tab, "Appearance")

    def _populate_fields(self) -> None:
        cfg = self._current_config
        self.f_pet_name.setText(cfg.get("pet_name", ""))
        self.f_buddy_skin.setCurrentText(cfg.get("buddy_skin", "skales"))
        self.f_hotkey.setText(cfg.get("activation_hotkey", ""))
        
        self.f_ai_enabled.setChecked(cfg.get("ai_enabled", True))
        self.f_memory_enabled.setChecked(cfg.get("memory_enabled", True))
        self.f_ollama_url.setText(cfg.get("ollama_base_url", ""))
        self.f_model.setText(cfg.get("ollama_model", ""))
        self.f_system_prompt.setPlainText(cfg.get("system_prompt", ""))
        
        self.f_proactive_enabled.setChecked(cfg.get("proactive_enabled", True))
        self.f_quiet_start.setValue(cfg.get("quiet_hours_start", 22))
        self.f_quiet_end.setValue(cfg.get("quiet_hours_end", 7))
        
        nt_cfg = cfg.get("notification_types", {})
        for nt, cb in self.f_types.items():
            cb.setChecked(nt_cfg.get(nt, True))
            
        w_size = cfg.get("window_size", [200, 200])
        self.f_window_size.setValue(w_size[0])
        self.f_frame_rate.setValue(cfg.get("frame_rate_ms", 150))
        self.f_bubble_timeout.setValue(cfg.get("speech_bubble_timeout_ms", 5000))
        self.f_opaque.setChecked(cfg.get("opaque_fallback", False))

        # Check for modifications
        self.f_buddy_skin.currentTextChanged.connect(self._check_restart_needed)
        self.f_window_size.valueChanged.connect(self._check_restart_needed)
        self.f_model.textChanged.connect(self._check_restart_needed)

    def _check_restart_needed(self, *args) -> None:
        if (self.f_buddy_skin.currentText() != self._original_config.get("buddy_skin") or
            self.f_window_size.value() != self._original_config.get("window_size", [200,200])[0] or
            self.f_model.text() != self._original_config.get("ollama_model")):
            self.restart_warning.show()
        else:
            self.restart_warning.hide()

    def _save_settings(self) -> None:
        cfg = self._current_config
        cfg["pet_name"] = self.f_pet_name.text().strip()
        cfg["buddy_skin"] = self.f_buddy_skin.currentText()
        cfg["activation_hotkey"] = self.f_hotkey.text().strip()
        
        cfg["ai_enabled"] = self.f_ai_enabled.isChecked()
        cfg["memory_enabled"] = self.f_memory_enabled.isChecked()
        cfg["ollama_base_url"] = self.f_ollama_url.text().strip()
        cfg["ollama_model"] = self.f_model.text().strip()
        cfg["system_prompt"] = self.f_system_prompt.toPlainText()
        
        cfg["proactive_enabled"] = self.f_proactive_enabled.isChecked()
        cfg["quiet_hours_start"] = self.f_quiet_start.value()
        cfg["quiet_hours_end"] = self.f_quiet_end.value()
        
        cfg["notification_types"] = {nt: cb.isChecked() for nt, cb in self.f_types.items()}
        
        sz = self.f_window_size.value()
        cfg["window_size"] = [sz, sz]
        cfg["frame_rate_ms"] = self.f_frame_rate.value()
        cfg["speech_bubble_timeout_ms"] = self.f_bubble_timeout.value()
        cfg["opaque_fallback"] = self.f_opaque.isChecked()

        # Validate required fields before saving
        if not cfg.get("ollama_base_url", "").strip():
            cfg["ollama_base_url"] = "http://localhost:11434"
        if not cfg.get("ollama_model", "").strip():
            cfg["ollama_model"] = "qwen2.5-coder:7b"
        if not cfg.get("activation_hotkey", "").strip():
            cfg["activation_hotkey"] = "ctrl+k"
        if not cfg.get("system_prompt", "").strip():
            from src.core.config_manager import DEFAULT_CONFIG
            cfg["system_prompt"] = DEFAULT_CONFIG["system_prompt"]

        try:
            config_path = get_app_root() / "config.json"
            config_path.write_text(json.dumps(cfg, indent=4), "utf-8")
            logger.info("Settings saved to %s", config_path)
            self._original_config = dict(cfg)
            self.restart_warning.hide()
            # Emit immutable proxy so consumers keep the same type guarantee
            self.settings_changed.emit(dict(cfg))
            self.hide()
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{e}")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        painter.setBrush(QColor(10, 10, 10, 245))  # match chat window black theme
        painter.setPen(QPen(QColor(60, 60, 60, 100), 1.0))
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

    def hideEvent(self, event) -> None:
        self.closed.emit()
        super().hideEvent(event)
