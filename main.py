"""
main.py — KIBO Virtual Pet entry point.

Wires all components together via Qt signals/slots and starts the event loop.

AI is optional. Set "ai_enabled": false in config.json to run KIBO in
system-monitor-only mode (no hotkey, no voice, no Ollama required).
"""

import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QLockFile, QMetaObject, Q_ARG, QTimer
from PySide6.QtWidgets import QApplication

from brain import Brain
from config_manager import load_config
from system_monitor import SystemMonitor
from ui_manager import UIManager
from tray_manager import TrayManager
from chat_window import ChatWindow
from memory_store import MemoryStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    lock_dir = Path.home() / ".kibo"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = QLockFile(str(lock_dir / "kibo.lock"))
    if not lock_file.tryLock(100):
        sys.exit(0)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    config = load_config()  # path resolved via get_app_root() in config_manager
    ai_enabled = config.get("ai_enabled", True)

    logger.info("KIBO starting. Pet name: %s | AI: %s | Skin: %s",
                config["pet_name"],
                "enabled" if ai_enabled else "disabled",
                config.get("buddy_skin", "skales"))

    # --- Core components (always created) ---
    brain = Brain(config)
    system_monitor = SystemMonitor(config)
    ui = UIManager(config)
    tray = TrayManager(config, app)
    chat_window = ChatWindow(config)
    memory_store = MemoryStore(config)

    # ── Core Wiring ───────────────────────────────────────────────────
    system_monitor.sensor_update.connect(brain.on_sensor_update)
    brain.brain_output.connect(ui.on_brain_output)
    
    # Animation finished signal → Brain (handles INTRO→IDLE and ACTING→IDLE)
    ui.animation_finished.connect(brain.on_animation_done)

    # ── Tray ──────────────────────────────────────────────────────────
    tray.show_chat.connect(chat_window.show)
    tray.hide_chat.connect(chat_window.hide)
    tray.quit_requested.connect(app.quit)
    ui.quit_requested.connect(app.quit)
    
    # Reset pet position
    tray.reset_position.connect(ui._reset_position)

    # ── Pet click → Chat ──────────────────────────────────────────────
    ui.pet_clicked.connect(chat_window.toggle)

    # --- AI components (only when ai_enabled=true) ---
    hotkey_thread = None
    voice_thread = None
    ai_thread = None
    tts_thread = None

    if ai_enabled:
        from ai_client import AIThread
        from hotkey_listener import HotkeyThread
        from tts_manager import TTSThread
        from voice_listener import VoiceThread

        hotkey_thread = HotkeyThread(config)
        voice_thread = VoiceThread(config)
        ai_thread = AIThread(config, memory_store=memory_store)
        tts_thread = TTSThread(config)

        # ── Chat input → AI (queued, thread-safe) ─────────────────────────
        chat_window.message_sent.connect(brain.on_thinking_started)
        chat_window.message_sent.connect(
            lambda t: QMetaObject.invokeMethod(
                ai_thread.client, "send_query",
                Qt.QueuedConnection, Q_ARG(str, t)
            )
        )

        # Hotkey -> Brain (listening) + VoiceThread (record)
        hotkey_thread.hotkey_pressed.connect(brain.on_listening_started)
        hotkey_thread.hotkey_pressed.connect(
            lambda: voice_thread._listener.on_hotkey_pressed()
        )

        # Voice transcript -> Brain (thinking) + AI (query)
        voice_thread.transcript_ready.connect(brain.on_thinking_started)
        voice_thread.transcript_ready.connect(
            lambda text: ai_thread.client.send_query(text)
        )
        voice_thread.error_occurred.connect(ui.on_ai_error)
        voice_thread.error_occurred.connect(lambda _: brain.on_ai_done())

        # ── AI → Chat + UI + Memory + TTS ────────────────────────────────────────────
        ai_thread.response_chunk.connect(ui.on_response_chunk)
        ai_thread.response_chunk.connect(chat_window.on_chunk)
        
        ai_thread.response_done.connect(brain.on_talking_started)
        ai_thread.response_done.connect(chat_window.on_response_done)
        ai_thread.response_done.connect(tts_thread.speak)
        ai_thread.response_done.connect(
            lambda t: QTimer.singleShot(0, lambda: memory_store.extract_facts_async(t))
        )
        
        ai_thread.error_occurred.connect(ui.on_ai_error)
        ai_thread.error_occurred.connect(chat_window.on_error)
        ai_thread.error_occurred.connect(lambda _: brain.on_ai_done())

        # TTS done -> back to sensor-driven state
        tts_thread.speech_done.connect(brain.on_ai_done)

        voice_thread.start()
        ai_thread.start()
        tts_thread.start()
        hotkey_thread.start()

        logger.info("AI enabled. Press %s to talk to KIBO.", config["activation_hotkey"])
    else:
        logger.info("AI disabled. KIBO will react to system state only.")

    # --- Start core ---
    system_monitor.start()
    ui.place_on_screen()
    ui.show()

    # Emit initial state (INTRO or IDLE) after UI is visible
    initial_output = brain.get_initial_output()
    ui.on_brain_output(initial_output)

    logger.info("KIBO is running. Right-click the pet to quit.")

    exit_code = app.exec()

    # --- Cleanup ---
    system_monitor.stop()
    if hotkey_thread:
        hotkey_thread.stop()
    if voice_thread:
        voice_thread.stop()
    if ai_thread:
        ai_thread.stop()
    if tts_thread:
        tts_thread.stop()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
