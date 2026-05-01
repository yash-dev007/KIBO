"""
onboarding_window.py — First-run onboarding dialog for KIBO.

Shown only when first_run_completed is False in config.  Walks the user
through six pages:
  1. Welcome
  2. Provider choice (Groq / Ollama / Mock)
  3. Voice & audio status
  4. Privacy & consent checkboxes
  5. Keyboard shortcuts
  6. Finish

On completion the dialog saves the user's choices to config.json and sets
first_run_completed=True.  If the dialog is dismissed without completing,
first_run_completed is left untouched.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.config_manager import get_app_root, get_user_data_dir
from src.system.provider_health import check_groq, check_ollama, check_microphone, check_piper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page builders — each returns a plain QWidget
# ---------------------------------------------------------------------------

_TITLE_STYLE = "font-size: 20px; font-weight: bold; color: #ffffff;"
_BODY_STYLE = "font-size: 13px; color: #cccccc; line-height: 1.5;"
_STATUS_OK = "color: #55cc88; font-size: 12px;"
_STATUS_FAIL = "color: #cc5555; font-size: 12px;"

DIALOG_STYLE = """
QDialog {
    background-color: #1e1e2e;
    border-radius: 12px;
}
QLabel {
    background: transparent;
}
QLineEdit {
    background: #2a2a3e;
    color: #e0e0f0;
    border: 1px solid #444466;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #7070cc;
}
QRadioButton {
    color: #ccccdd;
    font-size: 13px;
    spacing: 8px;
}
QCheckBox {
    color: #ccccdd;
    font-size: 13px;
    spacing: 8px;
}
QCheckBox:disabled {
    color: #666677;
}
QPushButton {
    background: #4040aa;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 22px;
    font-size: 13px;
}
QPushButton:hover {
    background: #5555cc;
}
QPushButton:disabled {
    background: #333355;
    color: #666688;
}
QPushButton#secondary {
    background: transparent;
    color: #8888aa;
    border: 1px solid #444466;
}
QPushButton#secondary:hover {
    border-color: #7777aa;
    color: #aaaacc;
}
QGroupBox {
    border: 1px solid #444466;
    border-radius: 8px;
    margin-top: 10px;
    padding: 10px;
    color: #ccccdd;
    font-size: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}
"""


def _make_label(text: str, style: str = _BODY_STYLE) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(style)
    return lbl


def _build_welcome_page() -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(30, 30, 30, 10)
    layout.setSpacing(16)

    layout.addWidget(_make_label("Welcome to KIBO", _TITLE_STYLE))
    layout.addWidget(_make_label(
        "KIBO is your AI desktop companion. It can remember things you tell it, "
        "respond by voice, and occasionally check in with you."
    ))
    layout.addWidget(_make_label(
        "KIBO uses Groq for fast cloud responses when you provide an API key, "
        "or Ollama for fully local operation."
    ))
    layout.addStretch()
    return page


def _build_provider_page(state: dict) -> tuple[QWidget, callable]:
    """Return (page_widget, get_provider_state_fn).

    get_provider_state_fn returns a dict with the current provider selection
    and credentials when called.
    """
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(30, 20, 30, 10)
    layout.setSpacing(12)

    layout.addWidget(_make_label("Choose your AI provider", _TITLE_STYLE))

    group = QGroupBox("Provider")
    group_layout = QVBoxLayout(group)
    group_layout.setSpacing(10)

    btn_groq = QRadioButton("Groq (cloud — fast)")
    btn_ollama = QRadioButton("Ollama (local)")
    btn_mock = QRadioButton("Demo / Mock mode")
    btn_group = QButtonGroup(page)
    btn_group.addButton(btn_groq, 0)
    btn_group.addButton(btn_ollama, 1)
    btn_group.addButton(btn_mock, 2)

    # Groq key input
    groq_widget = QWidget()
    groq_layout = QVBoxLayout(groq_widget)
    groq_layout.setContentsMargins(20, 0, 0, 0)
    groq_layout.setSpacing(4)
    groq_key_input = QLineEdit()
    groq_key_input.setPlaceholderText("gsk_…")
    groq_key_input.setEchoMode(QLineEdit.Password)
    groq_layout.addWidget(_make_label("Groq API key:", "color:#aaaacc;font-size:12px;"))
    groq_layout.addWidget(groq_key_input)

    # Ollama host input
    ollama_widget = QWidget()
    ollama_layout = QVBoxLayout(ollama_widget)
    ollama_layout.setContentsMargins(20, 0, 0, 0)
    ollama_layout.setSpacing(4)
    ollama_host_input = QLineEdit()
    ollama_host_input.setText("http://localhost:11434")
    ollama_layout.addWidget(_make_label("Ollama host:", "color:#aaaacc;font-size:12px;"))
    ollama_layout.addWidget(ollama_host_input)

    # Status label + test button
    status_label = QLabel("")
    status_label.setStyleSheet(_STATUS_OK)
    status_label.setWordWrap(True)

    test_btn = QPushButton("Test Connection")
    test_btn.setObjectName("secondary")

    def _run_test() -> None:
        if btn_groq.isChecked():
            result = check_groq(groq_key_input.text().strip() or None)
        elif btn_ollama.isChecked():
            result = check_ollama(ollama_host_input.text().strip())
        else:
            status_label.setText("Mock mode — no connection needed.")
            status_label.setStyleSheet(_STATUS_OK)
            return
        if result["available"]:
            status_label.setStyleSheet(_STATUS_OK)
            status_label.setText(f"OK: {result['reason']}")
        else:
            status_label.setStyleSheet(_STATUS_FAIL)
            status_label.setText(f"Failed: {result['reason']}")

    test_btn.clicked.connect(_run_test)

    def _on_radio_changed(_id: int) -> None:
        groq_widget.setVisible(_id == 0)
        ollama_widget.setVisible(_id == 1)
        status_label.setText("")

    btn_group.idClicked.connect(_on_radio_changed)

    # Default selection
    btn_mock.setChecked(True)
    groq_widget.setVisible(False)
    ollama_widget.setVisible(False)

    group_layout.addWidget(btn_groq)
    group_layout.addWidget(groq_widget)
    group_layout.addWidget(btn_ollama)
    group_layout.addWidget(ollama_widget)
    group_layout.addWidget(btn_mock)
    layout.addWidget(group)

    test_row = QHBoxLayout()
    test_row.addWidget(test_btn)
    test_row.addWidget(status_label)
    test_row.addStretch()
    layout.addLayout(test_row)
    layout.addStretch()

    def get_state() -> dict:
        if btn_groq.isChecked():
            return {
                "llm_provider": "groq",
                "_groq_api_key_raw": groq_key_input.text().strip(),
            }
        if btn_ollama.isChecked():
            return {
                "llm_provider": "ollama",
                "ollama_base_url": ollama_host_input.text().strip(),
            }
        return {"llm_provider": "mock"}

    return page, get_state


def _build_privacy_page() -> tuple[QWidget, callable]:
    """Return (page_widget, get_consent_state_fn)."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(30, 20, 30, 10)
    layout.setSpacing(14)

    layout.addWidget(_make_label("Privacy & Consent", _TITLE_STYLE))
    layout.addWidget(_make_label(
        "All features below are opt-in. You can change them anytime in Settings."
    ))

    cb_memory = QCheckBox("Enable memory (KIBO remembers facts from conversations)")
    cb_memory.setChecked(False)

    cb_proactive = QCheckBox(
        "Enable proactive check-ins (KIBO may speak without being asked)"
    )
    cb_proactive.setChecked(False)

    cb_calendar = QCheckBox("Enable Google Calendar integration")
    cb_calendar.setChecked(False)
    cb_calendar.setEnabled(False)
    cb_calendar.setToolTip("Connect in Settings after setup")

    cal_note = _make_label(
        "  (Connect in Settings after setup)",
        "font-size:11px; color:#666688; font-style:italic;"
    )

    data_dir = Path.home() / ".kibo"
    layout.addWidget(cb_memory)
    layout.addWidget(cb_proactive)
    layout.addWidget(cb_calendar)
    layout.addWidget(cal_note)
    layout.addSpacing(8)
    layout.addWidget(_make_label(
        f"Your data is stored in: {data_dir}",
        "font-size:11px; color:#888899;"
    ))
    layout.addStretch()

    def get_state() -> dict:
        return {
            "memory_enabled": cb_memory.isChecked(),
            "proactive_enabled": cb_proactive.isChecked(),
        }

    return page, get_state


def _build_voice_page(config: dict) -> QWidget:
    """Show microphone and TTS availability — auto-checked, no audio played."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(30, 20, 30, 10)
    layout.setSpacing(14)

    layout.addWidget(_make_label("Voice & Audio", _TITLE_STYLE))
    layout.addWidget(_make_label(
        "KIBO uses your microphone for push-to-talk and Piper (or pyttsx3) for speech."
    ))

    # Microphone status
    mic_result = check_microphone()
    mic_style = _STATUS_OK if mic_result["available"] else _STATUS_FAIL
    mic_icon = "✓" if mic_result["available"] else "✗"
    layout.addWidget(_make_label(
        f"{mic_icon} Microphone: {mic_result['reason']}", mic_style
    ))

    # Piper status
    piper_model = config.get("piper_model", "")
    piper_dir = config.get("piper_models_dir", "models/piper")
    piper_path = str(Path(piper_dir) / f"{piper_model}.onnx") if piper_model else None
    piper_result = check_piper(piper_path)
    piper_style = _STATUS_OK if piper_result["available"] else _STATUS_FAIL
    piper_icon = "✓" if piper_result["available"] else "✗"
    layout.addWidget(_make_label(
        f"{piper_icon} Piper TTS: {piper_result['reason']}", piper_style
    ))

    if not piper_result["available"]:
        layout.addWidget(_make_label(
            "  pyttsx3 will be used as fallback — voice will work but sound robotic.",
            "font-size:11px; color:#888899; font-style:italic;"
        ))

    layout.addStretch()
    return page


def _build_hotkeys_page(config: dict) -> QWidget:
    """Display current hotkeys. Hotkey changes require restart."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(30, 20, 30, 10)
    layout.setSpacing(14)

    layout.addWidget(_make_label("Keyboard Shortcuts", _TITLE_STYLE))
    layout.addWidget(_make_label(
        "These hotkeys let you talk to KIBO and capture clips."
    ))

    talk_hotkey = config.get("activation_hotkey", "ctrl+k")
    clip_hotkey = config.get("clip_hotkey", "ctrl+alt+k")

    group = QGroupBox("Current hotkeys")
    group_layout = QVBoxLayout(group)
    group_layout.addWidget(_make_label(
        f"Talk / Push-to-talk:  {talk_hotkey}",
        "font-size: 13px; color: #ddddff;"
    ))
    group_layout.addWidget(_make_label(
        f"Capture clip:  {clip_hotkey}",
        "font-size: 13px; color: #ddddff;"
    ))
    layout.addWidget(group)

    layout.addWidget(_make_label(
        "To change hotkeys: open Settings → General after setup. "
        "Hotkey changes take effect after a restart.",
        "font-size:11px; color:#888899; font-style:italic;"
    ))

    layout.addWidget(_make_label(
        "If a hotkey fails to register (e.g. already in use by another app), "
        "KIBO will log a warning and you can rebind it in Settings.",
        "font-size:11px; color:#888899; font-style:italic;"
    ))

    layout.addStretch()
    return page


def _build_finish_page() -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(30, 30, 30, 10)
    layout.setSpacing(16)

    layout.addWidget(_make_label("KIBO is ready!", _TITLE_STYLE))
    layout.addWidget(_make_label(
        "You can change all settings anytime from the tray icon."
    ))
    layout.addStretch()
    return page


# ---------------------------------------------------------------------------
# OnboardingWindow
# ---------------------------------------------------------------------------

class OnboardingWindow(QDialog):
    """Multi-step first-run onboarding dialog.

    Accepts the current config dict.  On successful completion (Finish button),
    writes updated values to config.json and sets first_run_completed=True.
    If closed early, config is not modified.
    """

    _PAGE_WELCOME = 0
    _PAGE_PROVIDER = 1
    _PAGE_VOICE = 2
    _PAGE_PRIVACY = 3
    _PAGE_HOTKEYS = 4
    _PAGE_FINISH = 5

    def __init__(self, config: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = dict(config)
        self._get_provider_state: Optional[callable] = None
        self._get_privacy_state: Optional[callable] = None
        self._completed = False

        self.setWindowTitle("KIBO — First Run Setup")
        self.setFixedSize(520, 460)
        self.setStyleSheet(DIALOG_STYLE)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowTitleHint
            | Qt.WindowCloseButtonHint
        )

        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Stacked pages
        self._stack = QStackedWidget()
        welcome_page = _build_welcome_page()
        provider_page, self._get_provider_state = _build_provider_page(self._config)
        voice_page = _build_voice_page(self._config)
        privacy_page, self._get_privacy_state = _build_privacy_page()
        hotkeys_page = _build_hotkeys_page(self._config)
        finish_page = _build_finish_page()

        self._stack.addWidget(welcome_page)
        self._stack.addWidget(provider_page)
        self._stack.addWidget(voice_page)
        self._stack.addWidget(privacy_page)
        self._stack.addWidget(hotkeys_page)
        self._stack.addWidget(finish_page)

        root.addWidget(self._stack, stretch=1)

        # Navigation row
        nav_widget = QWidget()
        nav_widget.setStyleSheet("background: #161622; border-top: 1px solid #333355;")
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(20, 12, 20, 12)

        self._back_btn = QPushButton("Back")
        self._back_btn.setObjectName("secondary")
        self._back_btn.setEnabled(False)
        self._back_btn.clicked.connect(self._go_back)

        self._next_btn = QPushButton("Next")
        self._next_btn.clicked.connect(self._go_next)

        nav_layout.addWidget(self._back_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self._next_btn)
        root.addWidget(nav_widget)

        self._update_nav_buttons()

    def _current_index(self) -> int:
        return self._stack.currentIndex()

    def _go_back(self) -> None:
        idx = self._current_index()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
        self._update_nav_buttons()

    def _go_next(self) -> None:
        idx = self._current_index()
        last = self._stack.count() - 1

        if idx == last:
            self._finish()
            return

        self._stack.setCurrentIndex(idx + 1)
        self._update_nav_buttons()

    def _update_nav_buttons(self) -> None:
        idx = self._current_index()
        last = self._stack.count() - 1
        self._back_btn.setEnabled(idx > 0)
        self._next_btn.setText("Finish" if idx == last else "Next")

    def _finish(self) -> None:
        """Collect all page states, merge into config, persist, and close."""
        updates: dict = {}

        if self._get_provider_state is not None:
            updates.update(self._get_provider_state())

        if self._get_privacy_state is not None:
            updates.update(self._get_privacy_state())

        updates["first_run_completed"] = True

        # Remove internal-only key used for raw key entry (not stored in config)
        raw_key = updates.pop("_groq_api_key_raw", None)

        self._persist_config(updates, raw_key)
        self._completed = True
        self.accept()

    def _persist_config(self, merged: dict, raw_groq_key: Optional[str]) -> None:
        """Write the updated config to config.json."""
        app_root = get_app_root()
        config_path = app_root / "config.json"

        try:
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as fh:
                    on_disk: dict = json.load(fh)
            else:
                on_disk = {}
        except Exception:
            on_disk = {}

        # Only write keys that differ from the on-disk version, plus the new ones
        on_disk.update({
            k: v for k, v in merged.items()
            if k not in ("_groq_api_key_raw",)
        })

        # If user provided a raw Groq key we do NOT store it in config.json.
        # We only store the env-var name.  A future improvement would write it
        # to a secrets file or prompt the user to set GROQ_API_KEY themselves.
        if raw_groq_key:
            logger.info(
                "Groq API key provided during onboarding. "
                "Store it as the GROQ_API_KEY environment variable for use by KIBO."
            )

        try:
            with config_path.open("w", encoding="utf-8") as fh:
                json.dump(on_disk, fh, indent=4, ensure_ascii=False)
            logger.info("Onboarding config saved to %s", config_path)
        except OSError as exc:
            logger.error("Failed to save onboarding config: %s", exc)

    def was_completed(self) -> bool:
        """Return True if the user clicked Finish (not just dismissed)."""
        return self._completed
