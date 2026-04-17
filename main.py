"""
main.py — KIBO Virtual Pet entry point.

Wires all components together via Qt signals/slots and starts the event loop.

AI is optional. Set "ai_enabled": false in config.json to run KIBO in
system-monitor-only mode (no hotkey, no voice, no Ollama required).
"""

import logging
import sys
import os
from pathlib import Path

# Force WMF backend to natively support VP9 WebM alpha videos provided by Web Media Extensions
os.environ["QT_MEDIA_BACKEND"] = "windows"

from PySide6.QtCore import Qt, QLockFile, QMetaObject, Q_ARG, QTimer
from PySide6.QtWidgets import QApplication

from src.ai.brain import Brain
from src.core.config_manager import load_config
from src.system.system_monitor import SystemMonitor
from src.ui.ui_manager import UIManager
from src.ui.tray_manager import TrayManager
from src.ui.chat_window import ChatWindow
from src.ai.memory_store import MemoryStore
from src.system.notification_router import NotificationRouter
from src.system.proactive_engine import ProactiveEngine
from src.ui.settings_window import SettingsWindow
from src.system.task_runner import TaskRunner
from src.system.calendar_manager import CalendarManager

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
    notification_router = NotificationRouter(config)
    proactive_engine = ProactiveEngine(config, router=notification_router)
    brain = Brain(config, router=notification_router)
    system_monitor = SystemMonitor(config)
    ui = UIManager(config)
    tray = TrayManager(config, app)
    chat_window = ChatWindow(config)
    memory_store = MemoryStore(config)
    settings_window = SettingsWindow(config)
    calendar_manager = CalendarManager(config)

    # ── Core Wiring ───────────────────────────────────────────────────
    system_monitor.sensor_update.connect(brain.on_sensor_update)
    system_monitor.sensor_update.connect(proactive_engine.on_sensor_update)
    brain.brain_output.connect(ui.on_brain_output)
    
    proactive_engine.proactive_notification.connect(notification_router.route)
    notification_router.notification_approved.connect(lambda msg, _: ui.show_notification(msg))
    
    # Animation finished signal → Brain (handles INTRO→IDLE and ACTING→IDLE)
    ui.animation_finished.connect(brain.on_animation_done)

    # ── Tray ──────────────────────────────────────────────────────────
    tray.show_chat.connect(chat_window.show)
    tray.hide_chat.connect(chat_window.hide)
    tray.quit_requested.connect(app.quit)
    ui.quit_requested.connect(app.quit)
    
    # Settings window
    ui.show_settings.connect(settings_window.show)
    settings_window.settings_changed.connect(ui.on_config_changed)
    settings_window.settings_changed.connect(system_monitor.on_config_changed)
    settings_window.clear_memory_requested.connect(memory_store.clear_all_facts)
    
    # Reset pet position + About from tray
    tray.reset_position.connect(ui.reset_position)
    tray.show_about.connect(ui.show_about)

    # ── Pet click → Chat ──────────────────────────────────────────────
    ui.pet_clicked.connect(chat_window.toggle)
    ui.pet_clicked.connect(proactive_engine.update_last_interaction)

    # --- AI components (only when ai_enabled=true) ---
    hotkey_thread = None
    voice_thread = None
    ai_thread = None
    tts_thread = None
    task_runner = None

    if ai_enabled:
        from src.ai.ai_client import AIThread
        from src.system.hotkey_listener import HotkeyThread
        from src.ai.tts_manager import TTSThread
        from src.ai.voice_listener import VoiceThread

        hotkey_thread = HotkeyThread(config)
        voice_thread = VoiceThread(config)
        ai_thread = AIThread(config, memory_store=memory_store)
        tts_thread = TTSThread(config)
        task_runner = TaskRunner(config, ai_client=ai_thread.client)

        # ── Mic button in chat → same flow as hardware hotkey ─────────────
        chat_window.mic_pressed.connect(brain.on_listening_started)
        chat_window.mic_pressed.connect(voice_thread._listener.on_hotkey_pressed)
        chat_window.mic_pressed.connect(lambda: tts_thread.manager.set_silent_mode(False))

        # ── Chat input → AI (queued, thread-safe) ─────────────────────────
        _is_text_chat = False

        def _handle_text_query(text: str) -> None:
            nonlocal _is_text_chat
            _is_text_chat = True
            ai_thread.cancel_current()  # abort any in-flight stream before starting new one
            tts_thread.manager.set_silent_mode(True)
            brain.on_thinking_started()  # show THINKING animation during text chat
            proactive_engine.update_last_interaction()
            QMetaObject.invokeMethod(
                ai_thread.client, "send_query",
                Qt.QueuedConnection,
                Q_ARG(str, text),
            )

        def _handle_voice_query(text: str) -> None:
            nonlocal _is_text_chat
            _is_text_chat = False
            tts_thread.manager.set_silent_mode(False)
            brain.on_thinking_started()
            QMetaObject.invokeMethod(
                ai_thread.client, "send_query",
                Qt.QueuedConnection,
                Q_ARG(str, text),
            )

        def _on_response_done(text: str) -> None:
            if not _is_text_chat:
                brain.on_talking_started(text)
            chat_window.on_response_done(text)
            QMetaObject.invokeMethod(
                tts_thread.manager, "speak",
                Qt.QueuedConnection,
                Q_ARG(str, text),
            )
            QTimer.singleShot(0, lambda: memory_store.extract_facts_async(text))

        chat_window.message_sent.connect(_handle_text_query)

        # Hotkey -> Brain (listening) + VoiceThread (record)
        hotkey_thread.hotkey_pressed.connect(brain.on_listening_started)
        hotkey_thread.hotkey_pressed.connect(voice_thread._listener.on_hotkey_pressed)
        hotkey_thread.hotkey_pressed.connect(lambda: tts_thread.manager.set_silent_mode(False))

        # Voice transcript -> Brain (thinking) + AI (query)
        voice_thread.transcript_ready.connect(_handle_voice_query)
        voice_thread.error_occurred.connect(ui.on_ai_error)
        voice_thread.error_occurred.connect(lambda _: brain.on_ai_done())

        # ── AI → Chat + UI + Memory + TTS ────────────────────────────────────────────
        ai_thread.response_chunk.connect(ui.on_response_chunk)
        ai_thread.response_chunk.connect(chat_window.on_chunk)
        
        ai_thread.response_done.connect(_on_response_done)
        
        ai_thread.error_occurred.connect(ui.on_ai_error)
        ai_thread.error_occurred.connect(chat_window.on_error)
        ai_thread.error_occurred.connect(lambda _: brain.on_ai_done())

        # TTS done -> back to sensor-driven state
        tts_thread.speech_done.connect(brain.on_ai_done)
        
        # ── Task Runner ───────────────────────────────────────────────────
        task_runner.task_completed.connect(proactive_engine.on_task_completed)
        task_runner.task_blocked.connect(proactive_engine.on_task_blocked)
        task_runner.task_blocked.connect(
            lambda task: chat_window.show_approval_prompt(task) if task.get("error") == "awaiting_approval" else None
        )
        chat_window.task_approved.connect(task_runner.approve_task)
        chat_window.task_cancelled.connect(task_runner.cancel_task)

        voice_thread.start()
        ai_thread.start()
        tts_thread.start()
        hotkey_thread.start()
        task_runner.start()

        logger.info("AI enabled. Press %s to talk to KIBO.", config["activation_hotkey"])
    else:
        logger.info("AI disabled. KIBO will react to system state only.")

    # ── Calendar → Proactive ──────────────────────────────────────────
    calendar_manager.events_updated.connect(proactive_engine.on_calendar_updated)

    # --- Start core ---
    system_monitor.start()
    calendar_manager.start()
    proactive_engine.start()
    ui.place_on_screen()
    ui.show()

    # Emit initial state (INTRO or IDLE) after UI is visible
    initial_output = brain.get_initial_output()
    ui.on_brain_output(initial_output)

    logger.info("KIBO is running. Right-click the pet to quit.")

    exit_code = app.exec()

    # --- Cleanup ---
    system_monitor.stop()
    calendar_manager.stop()
    proactive_engine.stop()
    if hotkey_thread:
        hotkey_thread.stop()
    if voice_thread:
        voice_thread.stop()
    if ai_thread:
        ai_thread.stop()
    if tts_thread:
        tts_thread.stop()
    if task_runner:
        task_runner.stop()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
