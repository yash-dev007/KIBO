import datetime
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QFormLayout, QCheckBox, QComboBox, QSpinBox, QSlider, QPlainTextEdit,
    QGraphicsDropShadowEffect, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QDialog, QDialogButtonBox, QAbstractItemView,
    QSizePolicy,
)

from src.core.config_manager import get_app_root, get_user_data_dir

logger = logging.getLogger(__name__)

class SettingsWindow(QWidget):
    settings_changed = Signal(dict)
    closed = Signal()
    clear_memory_requested = Signal()

    @staticmethod
    def _discover_skins() -> list[str]:
        """Return sorted list of skin names from assets/animations/."""
        from src.core.config_manager import get_bundle_dir
        anim_dir = get_bundle_dir() / "assets" / "animations"
        if not anim_dir.is_dir():
            return ["skales"]
        skins = sorted(
            d.name for d in anim_dir.iterdir()
            if d.is_dir() and (d / "idle").is_dir()
        )
        return skins if skins else ["skales"]

    def __init__(self, config: dict, parent: Optional[QWidget] = None, memory_store=None) -> None:
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(520, 640)
        self._original_config = config
        self._current_config = dict(config)
        self._drag_pos: Optional[QPoint] = None
        self._memory_store = memory_store

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
        self._init_memory_tab()
        self._init_data_tab()
        self.tabs.currentChanged.connect(self._on_tab_changed)

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
        self.f_buddy_skin.addItems(self._discover_skins())
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

    def _init_memory_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Search bar
        search_row = QHBoxLayout()
        self._mem_search = QLineEdit()
        self._mem_search.setPlaceholderText("Search memories...")
        self._mem_search.textChanged.connect(self._filter_memory_table)
        search_row.addWidget(self._mem_search)
        layout.addLayout(search_row)

        # Table
        self._mem_table = QTableWidget(0, 3)
        self._mem_table.setHorizontalHeaderLabels(["Category", "Content", "Date"])
        self._mem_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._mem_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._mem_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._mem_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._mem_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._mem_table.verticalHeader().setVisible(False)
        self._mem_table.setStyleSheet("""
            QTableWidget { gridline-color: rgba(60,60,60,100); }
            QTableWidget::item { padding: 4px; }
            QHeaderView::section {
                background: rgba(30,30,30,200);
                color: #aaaaaa;
                padding: 4px;
                border: none;
                font-size: 11px;
            }
        """)
        layout.addWidget(self._mem_table)

        # Empty state label
        self._mem_empty = QLabel("No memories yet.")
        self._mem_empty.setAlignment(Qt.AlignCenter)
        self._mem_empty.setStyleSheet("color: #666; font-size: 13px;")
        self._mem_empty.hide()
        layout.addWidget(self._mem_empty)

        # Action buttons row
        btn_row = QHBoxLayout()

        btn_edit = QPushButton("Edit Selected")
        btn_edit.setCursor(Qt.PointingHandCursor)
        btn_edit.setStyleSheet(self._action_btn_style())
        btn_edit.clicked.connect(self._on_edit_memory)

        btn_delete = QPushButton("Delete Selected")
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.setStyleSheet(self._destructive_btn_style())
        btn_delete.clicked.connect(self._on_delete_memory)

        btn_vault = QPushButton("Open Vault")
        btn_vault.setCursor(Qt.PointingHandCursor)
        btn_vault.setStyleSheet(self._action_btn_style())
        btn_vault.clicked.connect(self._on_open_vault)

        btn_rebuild = QPushButton("Rebuild Index")
        btn_rebuild.setCursor(Qt.PointingHandCursor)
        btn_rebuild.setStyleSheet(self._action_btn_style())
        btn_rebuild.clicked.connect(self._on_rebuild_index)

        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_delete)
        btn_row.addStretch()
        btn_row.addWidget(btn_vault)
        btn_row.addWidget(btn_rebuild)
        layout.addLayout(btn_row)

        self.tabs.addTab(tab, "Memory")
        self._mem_tab_index = self.tabs.count() - 1

    def _action_btn_style(self) -> str:
        return """
            QPushButton {
                background: rgba(50,50,50,150);
                border: 1px solid rgba(90,90,90,100);
                border-radius: 4px;
                color: #e0e0e0;
                padding: 4px 8px;
            }
            QPushButton:hover { background: rgba(80,80,80,200); }
        """

    def _destructive_btn_style(self) -> str:
        return """
            QPushButton {
                background: rgba(150,40,40,100);
                border: 1px solid rgba(200,50,50,100);
                border-radius: 4px;
                color: white;
                padding: 4px 8px;
            }
            QPushButton:hover { background: rgba(200,50,50,150); }
        """

    def _on_tab_changed(self, index: int) -> None:
        if hasattr(self, "_mem_tab_index") and index == self._mem_tab_index:
            self._refresh_memory_table()

    def _refresh_memory_table(self) -> None:
        if self._memory_store is None:
            self._mem_table.setRowCount(0)
            self._mem_empty.setText("Memory store not available.")
            self._mem_empty.show()
            return

        facts = self._memory_store.list_facts()
        self._mem_table.setRowCount(0)

        query = self._mem_search.text().lower().strip()
        visible = [
            f for f in facts
            if not query or query in f.get("content", "").lower() or query in f.get("category", "").lower()
        ]

        if not visible:
            self._mem_empty.show()
        else:
            self._mem_empty.hide()

        for row, fact in enumerate(visible):
            self._mem_table.insertRow(row)
            cat_item = QTableWidgetItem(fact.get("category", ""))
            cat_item.setData(Qt.UserRole, fact.get("id", ""))
            content_preview = fact.get("content", "")[:80]
            content_item = QTableWidgetItem(content_preview)
            ts = fact.get("extracted_at", 0)
            if ts:
                date_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            else:
                date_str = fact.get("source_session", "")
            date_item = QTableWidgetItem(date_str)
            self._mem_table.setItem(row, 0, cat_item)
            self._mem_table.setItem(row, 1, content_item)
            self._mem_table.setItem(row, 2, date_item)

    def _filter_memory_table(self, _text: str) -> None:
        self._refresh_memory_table()

    def _selected_fact_id(self) -> Optional[str]:
        row = self._mem_table.currentRow()
        if row < 0:
            return None
        item = self._mem_table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _on_edit_memory(self) -> None:
        if self._memory_store is None:
            return
        fact_id = self._selected_fact_id()
        if fact_id is None:
            QMessageBox.information(self, "No selection", "Select a memory row to edit.")
            return

        facts = self._memory_store.list_facts()
        fact = next((f for f in facts if str(f.get("id", "")) == fact_id), None)
        if fact is None:
            QMessageBox.warning(self, "Not found", "Memory not found.")
            self._refresh_memory_table()
            return

        dlg = _MemoryEditDialog(fact, self)
        if dlg.exec() != QDialog.Accepted:
            return

        changes = dlg.get_changes()
        ok = self._memory_store.update_fact(fact_id, changes)
        if not ok:
            QMessageBox.warning(self, "Error", "Failed to update memory.")
        self._refresh_memory_table()

    def _on_delete_memory(self) -> None:
        if self._memory_store is None:
            return
        fact_id = self._selected_fact_id()
        if fact_id is None:
            QMessageBox.information(self, "No selection", "Select a memory row to delete.")
            return

        ok = self._memory_store.delete_fact(fact_id)
        if not ok:
            QMessageBox.warning(self, "Not found", "Memory could not be deleted.")
        self._refresh_memory_table()

    def _on_open_vault(self) -> None:
        if self._memory_store is None:
            return
        vault_path = self._memory_store.get_vault_path()
        self._open_data_folder(vault_path)

    def _on_rebuild_index(self) -> None:
        if self._memory_store is None:
            return
        self._memory_store.rebuild_index()
        QMessageBox.information(self, "Done", "Memory index rebuilt from vault.")
        self._refresh_memory_table()

    def _init_data_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        data_dir = get_user_data_dir()
        path_label = QLabel(f"Data location: {data_dir}")
        path_label.setWordWrap(True)
        path_label.setStyleSheet("color: #888899; font-size: 12px;")
        layout.addWidget(path_label)

        btn_open_folder = QPushButton("Open Data Folder")
        btn_open_folder.setCursor(Qt.PointingHandCursor)
        btn_open_folder.clicked.connect(lambda: self._open_data_folder(data_dir))
        layout.addWidget(btn_open_folder)

        btn_reset_onboarding = QPushButton("Reset Onboarding")
        btn_reset_onboarding.setCursor(Qt.PointingHandCursor)
        btn_reset_onboarding.setStyleSheet("""
            QPushButton {
                background: rgba(100, 80, 20, 100);
                border: 1px solid rgba(160, 130, 30, 100);
                border-radius: 4px;
                color: white;
                padding: 4px 8px;
            }
            QPushButton:hover { background: rgba(140, 110, 20, 150); }
        """)
        btn_reset_onboarding.clicked.connect(self._on_reset_onboarding)
        layout.addWidget(btn_reset_onboarding)

        layout.addStretch()
        self.tabs.addTab(tab, "Data")

    def _open_data_folder(self, path: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            logger.error("Could not open data folder: %s", exc)
            QMessageBox.warning(self, "Error", f"Could not open folder:\n{exc}")

    def _on_reset_onboarding(self) -> None:
        reply = QMessageBox.question(
            self, "Reset Onboarding",
            "This will show the first-run setup wizard on next launch. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            config_path = get_app_root() / "config.json"
            data: dict = {}
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            data["first_run_completed"] = False
            with config_path.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "Done", "Onboarding will run on next launch.")
        except Exception as exc:
            logger.error("Failed to reset onboarding: %s", exc)
            QMessageBox.critical(self, "Error", f"Failed to reset onboarding:\n{exc}")

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


class _MemoryEditDialog(QDialog):
    """Small dialog for editing a single memory fact."""

    _CATEGORIES = ["preference", "fact", "person", "location", "task"]

    def __init__(self, fact: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Memory")
        self.setMinimumWidth(420)
        self._fact = fact
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()

        self._content_edit = QPlainTextEdit()
        self._content_edit.setPlainText(self._fact.get("content", ""))
        self._content_edit.setFixedHeight(80)
        form.addRow("Content:", self._content_edit)

        self._category_combo = QComboBox()
        self._category_combo.addItems(self._CATEGORIES)
        current_cat = self._fact.get("category", "fact")
        if current_cat not in self._CATEGORIES:
            self._category_combo.addItem(current_cat)
        self._category_combo.setCurrentText(current_cat)
        form.addRow("Category:", self._category_combo)

        self._keywords_edit = QLineEdit()
        kw = self._fact.get("keywords", [])
        self._keywords_edit.setText(", ".join(kw) if isinstance(kw, list) else str(kw))
        self._keywords_edit.setPlaceholderText("comma-separated keywords")
        form.addRow("Keywords:", self._keywords_edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_changes(self) -> dict:
        raw_kw = [k.strip() for k in self._keywords_edit.text().split(",") if k.strip()]
        return {
            "content": self._content_edit.toPlainText().strip(),
            "category": self._category_combo.currentText(),
            "keywords": raw_kw,
        }
