from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from pathlib import Path

from src.core.config_manager import get_bundle_dir

class TrayManager(QObject):
    show_chat = Signal()
    hide_chat = Signal()
    show_settings = Signal()
    show_about = Signal()
    quit_requested = Signal()
    reset_position = Signal()

    def __init__(self, config: dict, app: QApplication) -> None:
        super().__init__()
        self._config = config
        self._app = app
        self._chat_visible = False

        self._tray = QSystemTrayIcon(self)
        icon_path = get_bundle_dir() / "assets" / "icons" / "tray.png"
        
        # If the icon doesn't exist, we can fallback to something or just not show an icon
        # For now, assume it will exist or QIcon handles missing files gracefully
        self._tray.setIcon(QIcon(str(icon_path)))
        self._tray.setToolTip("KIBO — AI Desktop Companion")

        self._menu = QMenu()

        self._toggle_chat_action = QAction("Open Chat", self)
        self._toggle_chat_action.triggered.connect(self._on_toggle_chat)
        self._menu.addAction(self._toggle_chat_action)
        
        self._menu.addSeparator()

        self._reset_pos_action = QAction("Reset Pet Position", self)
        self._reset_pos_action.triggered.connect(self.reset_position.emit)
        self._menu.addAction(self._reset_pos_action)

        self._about_action = QAction("About KIBO", self)
        self._about_action.triggered.connect(self.show_about.emit)
        self._menu.addAction(self._about_action)

        self._menu.addSeparator()

        self._quit_action = QAction("Quit", self)
        self._quit_action.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(self._quit_action)

        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)

        self._tray.show()

    def _on_toggle_chat(self) -> None:
        if self._chat_visible:
            self.hide_chat.emit()
        else:
            self.show_chat.emit()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._on_toggle_chat()

    def set_chat_visible(self, visible: bool) -> None:
        self._chat_visible = visible
        if visible:
            self._toggle_chat_action.setText("Hide Chat")
        else:
            self._toggle_chat_action.setText("Open Chat")
