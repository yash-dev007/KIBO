"""
main.py — KIBO Virtual Pet entry point.

Wires all components together via Qt signals/slots and starts the event loop.

AI is optional. Set "ai_enabled": false in config.json to run KIBO in
system-monitor-only mode (no hotkey, no voice, no Ollama required).
"""

import logging
from logging.handlers import RotatingFileHandler
import sys
import os
import re
from pathlib import Path

# Force WMF backend to natively support VP9 WebM alpha videos provided by Web Media Extensions
os.environ["QT_MEDIA_BACKEND"] = "windows"

from PySide6.QtCore import Qt, QLockFile, QMetaObject, Q_ARG, QTimer
from PySide6.QtWidgets import QApplication

from src.ai.brain import Brain
from src.core.config_manager import get_user_data_dir, load_config
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

def _configure_logging() -> None:
    logs_dir = get_user_data_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        logs_dir / "kibo.log",
        maxBytes=512_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])


_configure_logging()
logger = logging.getLogger(__name__)


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

    config = load_config()  # path resolved via get_app_root() in config_manager

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

    # --- Core components (always created) ---
    notification_router = NotificationRouter(config)
    proactive_engine = ProactiveEngine(config, router=notification_router)
    brain = Brain(config, router=notification_router)
    system_monitor = SystemMonitor(config)
    ui = UIManager(config)
    tray = TrayManager(config, app)
    chat_window = ChatWindow(config)
    memory_store = MemoryStore(config)
    settings_window = SettingsWindow(config, memory_store=memory_store)
    calendar_manager = CalendarManager(config)

    # ── Core Wiring ───────────────────────────────────────────────────
    system_monitor.sensor_update.connect(brain.on_sensor_update)
    system_monitor.sensor_update.connect(proactive_engine.on_sensor_update)
    brain.brain_output.connect(ui.on_brain_output)
    
    proactive_engine.proactive_notification.connect(notification_router.route)
    notification_router.notification_approved.connect(lambda msg, _: ui.show_notification(msg))

    def _snooze_proactivity() -> None:
        notification_router.snooze(hours=1)
        ui.show_notification("Okay, I'll stay quiet for an hour.")

    def _disable_proactivity() -> None:
        notification_router.disable_proactivity()
        ui.show_notification("Proactivity is off for this session.")

    ui.snooze_proactivity.connect(_snooze_proactivity)
    tray.snooze_proactivity.connect(_snooze_proactivity)
    ui.disable_proactivity.connect(_disable_proactivity)
    tray.disable_proactivity.connect(_disable_proactivity)
    
    # Animation finished signal → Brain (handles INTRO→IDLE and ACTING→IDLE)
    ui.animation_finished.connect(brain.on_animation_done)

    # ── Tray ──────────────────────────────────────────────────────────
    tray.show_chat.connect(chat_window.show)
    tray.hide_chat.connect(chat_window.hide)
    tray.show_settings.connect(settings_window.show)
    tray.quit_requested.connect(app.quit)
    ui.quit_requested.connect(app.quit)
    chat_window.visibility_changed.connect(tray.set_chat_visible)
    
    # Settings window
    ui.show_settings.connect(settings_window.show)
    settings_window.settings_changed.connect(ui.on_config_changed)
    settings_window.settings_changed.connect(brain.on_config_changed)
    settings_window.settings_changed.connect(system_monitor.on_config_changed)
    settings_window.settings_changed.connect(notification_router.on_config_changed)
    settings_window.settings_changed.connect(proactive_engine.on_config_changed)
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

        hotkey_thread = HotkeyThread(config)
        voice_thread = VoiceThread(config)
        ai_thread = AIThread(config, memory_store=memory_store)
        tts_thread = TTSThread(config)
        task_runner = TaskRunner(config, ai_client=ai_thread.client)
        sentence_buffer = SentenceBuffer()

        def _interrupt_current_turn() -> None:
            sentence_buffer.reset()
            ai_thread.cancel_current()
            tts_thread.interrupt()

        # ── Mic button in chat → same flow as hardware hotkey ─────────────
        chat_window.mic_pressed.connect(_interrupt_current_turn)
        chat_window.mic_pressed.connect(brain.on_listening_started)
        chat_window.mic_pressed.connect(voice_thread.on_hotkey_pressed)
        chat_window.mic_pressed.connect(lambda: tts_thread.manager.set_silent_mode(False))
        
        settings_window.settings_changed.connect(ai_thread.on_config_changed)
        settings_window.test_voice_requested.connect(tts_thread.test_voice)
        settings_window.voice_warmup_requested.connect(voice_thread.warm_up)

        # ── Chat input → AI (queued, thread-safe) ─────────────────────────
        _is_text_chat = False

        def _handle_text_query(text: str) -> None:
            nonlocal _is_text_chat
            _is_text_chat = True
            sentence_buffer.reset()  # clear any leftover from previous turn
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
            sentence_buffer.reset()  # clear any leftover from previous turn
            ai_thread.cancel_current()  # abort any in-flight stream before starting new one
            tts_thread.interrupt()  # discard queued speech from the previous turn
            tts_thread.manager.set_silent_mode(False)
            brain.on_thinking_started()
            QMetaObject.invokeMethod(
                ai_thread.client, "send_query",
                Qt.QueuedConnection,
                Q_ARG(str, text),
            )

        def _on_response_done(text: str) -> None:
            clean_text = _sanitize_assistant_text(text)
            if not _is_text_chat:
                brain.on_talking_started(clean_text)
            chat_window.on_response_done(clean_text)
            ui.on_response_done(clean_text)
            # Flush any tail sentence to TTS; speech_done emits when drained.
            sentence_buffer.flush()
            # Legacy fallback: if inline extraction is OFF, do the old async call.
            if not config.get("memory_extraction_inline", True):
                QTimer.singleShot(0, lambda: memory_store.extract_facts_async(clean_text))

        chat_window.message_sent.connect(_handle_text_query)

        # Hotkey -> Brain (listening) + VoiceThread (record)
        hotkey_thread.hotkey_pressed.connect(_interrupt_current_turn)
        hotkey_thread.hotkey_pressed.connect(brain.on_listening_started)
        hotkey_thread.hotkey_pressed.connect(voice_thread.on_hotkey_pressed)
        hotkey_thread.hotkey_pressed.connect(lambda: tts_thread.manager.set_silent_mode(False))

        # Clip hotkey → ClipRecorder
        hotkey_thread.clip_hotkey_pressed.connect(clip_recorder.dump)
        hotkey_thread.registration_failed.connect(
            lambda hotkey: ui.on_ai_error(f"Hotkey failed to register: {hotkey}")
        )
        settings_window.settings_changed.connect(
            lambda cfg: hotkey_thread.rebind(
                cfg.get("activation_hotkey", "ctrl+k"),
                cfg.get("clip_hotkey", "ctrl+alt+k"),
            )
        )

        # Voice thread states -> UI
        voice_thread.recording_started.connect(chat_window.show_listening_indicator)
        voice_thread.transcript_ready.connect(chat_window.update_voice_transcript)
        voice_thread.error_occurred.connect(chat_window.cancel_listening)

        # Voice transcript -> Brain (thinking) + AI (query)
        voice_thread.transcript_ready.connect(_handle_voice_query)
        voice_thread.error_occurred.connect(ui.on_ai_error)
        voice_thread.error_occurred.connect(lambda _: brain.on_ai_done())

        # ── AI → Chat + UI + Memory + TTS ────────────────────────────────────────────
        ai_thread.response_chunk.connect(ui.on_response_chunk)
        ai_thread.response_chunk.connect(chat_window.on_chunk)

        # Streaming: token deltas → sentence buffer → TTS chunk-at-a-time.
        # Voice replies stream; text-chat replies stay silent (set by silent_mode).
        ai_thread.response_chunk.connect(sentence_buffer.push)
        sentence_buffer.sentence_ready.connect(tts_thread.speak_chunk)
        # When the buffer is flushed (end of reply), signal the TTS drain to finish.
        sentence_buffer.flushed.connect(tts_thread.end_stream)

        ai_thread.response_done.connect(_on_response_done)

        # Inline memory: every `remember` tool-call from the LLM lands here.
        ai_thread.memory_fact_extracted.connect(memory_store.add_fact_inline)

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
        if config.get("voice_warmup_on_launch", True):
            QTimer.singleShot(250, voice_thread.warm_up)

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
