"""
main.py — KIBO Virtual Pet entry point.

Wires all components together via EventBus (backend) and Qt signals (UI),
then starts the Qt event loop.

AI is optional. Set "ai_enabled": false in config.json to run KIBO in
system-monitor-only mode (no hotkey, no voice, no Ollama required).
"""

import logging
import sys
import os
import re
from pathlib import Path

# Force WMF backend to natively support VP9 WebM alpha videos provided by Web Media Extensions
os.environ["QT_MEDIA_BACKEND"] = "windows"

from PySide6.QtCore import Qt, QLockFile, QTimer
from PySide6.QtWidgets import QApplication

from src.ai.brain import Brain
from src.api.event_bus import EventBus
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


def qt_safe(fn):
    """Wrap fn so it runs on the Qt main thread via QTimer.singleShot(0)."""
    def _wrapper(*args):
        QTimer.singleShot(0, lambda: fn(*args))
    return _wrapper


def _sanitize_assistant_text(text: str) -> str:
    """Remove lightweight roleplay/stage-direction fragments from model output."""
    cleaned = re.sub(r"\(\s*\*.*?\*\s*\)", " ", text, flags=re.DOTALL)
    cleaned = re.sub(r"\*[^*\n]{1,120}\*", " ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned)
    cleaned = cleaned.strip()
    return cleaned or text.strip()


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

    config = load_config()

    if not config.get("first_run_completed", False):
        from src.ui.onboarding_window import OnboardingWindow
        onboarding = OnboardingWindow(dict(config))
        onboarding.exec()
        config = load_config()

    ai_enabled = config.get("ai_enabled", True)

    logger.info("KIBO starting. Pet name: %s | AI: %s | Skin: %s",
                config["pet_name"],
                "enabled" if ai_enabled else "disabled",
                config.get("buddy_skin", "skales"))

    # ── EventBus (shared backbone) ────────────────────────────────────────
    bus = EventBus()

    # --- Core backend components ---
    notification_router = NotificationRouter(config, event_bus=bus)
    proactive_engine = ProactiveEngine(config, router=notification_router, event_bus=bus)
    brain = Brain(config, router=notification_router, event_bus=bus)
    system_monitor = SystemMonitor(config, event_bus=bus)
    memory_store = MemoryStore(config, event_bus=bus)
    calendar_manager = CalendarManager(config, event_bus=bus)

    # --- Qt UI components (unchanged Qt objects) ---
    ui = UIManager(config)
    tray = TrayManager(config, app)
    chat_window = ChatWindow(config)
    settings_window = SettingsWindow(config)

    # ── Backend EventBus wiring ───────────────────────────────────────────
    bus.on("sensor_update", brain.on_sensor_update)
    bus.on("sensor_update", proactive_engine.on_sensor_update)
    bus.on("events_updated", proactive_engine.on_calendar_updated)
    bus.on("task_completed", proactive_engine.on_task_completed)
    bus.on("task_blocked", proactive_engine.on_task_blocked)

    # ── Backend → Qt UI bridge (qt_safe marshals to main thread) ─────────
    bus.on("brain_output", qt_safe(ui.on_brain_output))
    bus.on("notification_approved",
           qt_safe(lambda msg, notif_type: ui.show_notification(msg)))
    bus.on("proactive_notification",
           qt_safe(lambda tp, msg, pri: notification_router.route(msg, tp)))

    # ── Tray / Qt-UI connections (all on main thread, no qt_safe needed) ──
    tray.show_chat.connect(chat_window.show)
    tray.hide_chat.connect(chat_window.hide)
    tray.quit_requested.connect(app.quit)
    ui.quit_requested.connect(app.quit)
    chat_window.visibility_changed.connect(tray.set_chat_visible)

    # Settings window
    ui.show_settings.connect(settings_window.show)
    settings_window.settings_changed.connect(ui.on_config_changed)
    settings_window.settings_changed.connect(
        lambda cfg: brain.on_config_changed(cfg))
    settings_window.settings_changed.connect(
        lambda cfg: system_monitor.on_config_changed(cfg))
    settings_window.settings_changed.connect(
        lambda cfg: notification_router.on_config_changed(cfg))
    settings_window.settings_changed.connect(
        lambda cfg: proactive_engine.on_config_changed(cfg))
    settings_window.clear_memory_requested.connect(memory_store.clear_all_facts)

    # Reset pet position + About from tray
    tray.reset_position.connect(ui.reset_position)
    tray.show_about.connect(ui.show_about)

    # Animation finished → Brain (pure-Python, no Qt needed)
    ui.animation_finished.connect(brain.on_animation_done)

    # Pet click → Chat + proactive
    ui.pet_clicked.connect(chat_window.toggle)
    ui.pet_clicked.connect(proactive_engine.update_last_interaction)

    # --- AI components (only when ai_enabled=true) ---
    hotkey_thread = None
    voice_thread = None
    ai_thread = None
    tts_thread = None
    task_runner = None

    # Clip recorder runs regardless of AI mode (records animation frames)
    from src.ui.clip_recorder import ClipRecorder
    clip_recorder = ClipRecorder()
    ui.frame_captured.connect(clip_recorder.on_frame)
    clip_recorder.clip_saved.connect(ui.show_clip_toast)
    clip_recorder.clip_error.connect(ui.show_clip_error)

    if ai_enabled:
        from src.ai.ai_client import AIThread
        from src.system.hotkey_listener import HotkeyThread
        from src.ai.tts_manager import TTSThread
        from src.ai.voice_listener import VoiceThread
        from src.ai.sentence_buffer import SentenceBuffer

        hotkey_thread = HotkeyThread(config, event_bus=bus)
        voice_thread = VoiceThread(config, event_bus=bus)
        ai_thread = AIThread(config, memory_store=memory_store, event_bus=bus)
        tts_thread = TTSThread(config, event_bus=bus)
        task_runner = TaskRunner(config, ai_client=ai_thread.client, event_bus=bus)
        sentence_buffer = SentenceBuffer(event_bus=bus)

        # ── Mic button in chat → same flow as hardware hotkey ─────────────
        chat_window.mic_pressed.connect(brain.on_listening_started)
        chat_window.mic_pressed.connect(voice_thread.on_hotkey_pressed)
        chat_window.mic_pressed.connect(
            lambda: tts_thread.manager.set_silent_mode(False))

        settings_window.settings_changed.connect(ai_thread.on_config_changed)

        # ── Chat text input → AI ──────────────────────────────────────────
        _is_text_chat = False

        def _handle_text_query(text: str) -> None:
            nonlocal _is_text_chat
            _is_text_chat = True
            ai_thread.cancel_current()
            tts_thread.manager.set_silent_mode(True)
            brain.on_thinking_started()
            proactive_engine.update_last_interaction()
            ai_thread.send_query(text)

        def _handle_voice_query(text: str) -> None:
            nonlocal _is_text_chat
            _is_text_chat = False
            tts_thread.manager.set_silent_mode(False)
            brain.on_thinking_started()
            ai_thread.send_query(text)

        def _on_response_done(text: str) -> None:
            clean_text = _sanitize_assistant_text(text)
            if not _is_text_chat:
                brain.on_talking_started(clean_text)
            chat_window.on_response_done(clean_text)
            ui.on_response_done(clean_text)
            sentence_buffer.flush()
            if not config.get("memory_extraction_inline", True):
                QTimer.singleShot(0, lambda: memory_store.extract_facts_async(clean_text))

        chat_window.message_sent.connect(_handle_text_query)

        # ── Hotkey → Brain + Voice ─────────────────────────────────────────
        bus.on("hotkey_pressed", qt_safe(brain.on_listening_started))
        bus.on("hotkey_pressed", voice_thread.on_hotkey_pressed)
        bus.on("hotkey_pressed",
               qt_safe(lambda: tts_thread.manager.set_silent_mode(False)))

        # Clip hotkey → ClipRecorder
        bus.on("clip_hotkey_pressed", qt_safe(clip_recorder.dump))

        # ── Voice states → UI (qt_safe — voice runs on daemon thread) ─────
        bus.on("recording_started",
               qt_safe(chat_window.show_listening_indicator))
        bus.on("transcript_ready",
               qt_safe(chat_window.update_voice_transcript))
        bus.on("error_occurred",
               qt_safe(chat_window.cancel_listening))

        # Voice transcript → AI (thread-safe via AIThread queue)
        bus.on("transcript_ready", _handle_voice_query)
        bus.on("error_occurred", qt_safe(ui.on_ai_error))
        bus.on("error_occurred", lambda _: brain.on_ai_done())

        # ── AI chunks → UI + sentence buffer ──────────────────────────────
        bus.on("response_chunk", qt_safe(ui.on_response_chunk))
        bus.on("response_chunk", qt_safe(chat_window.on_chunk))
        bus.on("response_chunk", sentence_buffer.push)

        # Sentence buffer → TTS (thread-safe via TTSThread queue)
        bus.on("sentence_ready", tts_thread.speak_chunk)
        bus.on("flushed", lambda: tts_thread.end_stream())

        # AI response done → UI + brain
        bus.on("response_done", qt_safe(_on_response_done))

        # Inline memory tool calls → store
        bus.on("memory_fact_extracted", memory_store.add_fact_inline)

        # AI errors → UI
        bus.on("error_occurred", qt_safe(chat_window.on_error))
        bus.on("error_occurred", lambda _: brain.on_ai_done())

        # TTS done → brain idle
        bus.on("speech_done", brain.on_ai_done)

        # ── Task Runner ───────────────────────────────────────────────────
        bus.on("task_blocked", qt_safe(
            lambda task: chat_window.show_approval_prompt(task)
            if task.get("error") == "awaiting_approval" else None
        ))
        chat_window.task_approved.connect(task_runner.approve_task)
        chat_window.task_cancelled.connect(task_runner.cancel_task)

        voice_thread.start()
        ai_thread.start()
        tts_thread.start()
        hotkey_thread.start()
        task_runner.start()

        logger.info("AI enabled. Press %s to talk to KIBO.", config["activation_hotkey"])
    else:
        task_runner = TaskRunner(config, None, event_bus=bus)
        logger.info("AI disabled. KIBO will react to system state only.")

    # --- Start core ---
    system_monitor.start()
    calendar_manager.start()
    proactive_engine.start()
    ui.place_on_screen()
    ui.show()

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
