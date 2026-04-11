"""
main.py — KIBO Virtual Pet entry point.

Wires all components together via Qt signals/slots and starts the event loop.

AI is optional. Set "ai_enabled": false in config.json to run KIBO in
system-monitor-only mode (no hotkey, no voice, no Ollama required).

Signal flow (when ai_enabled=true):
  HotkeyThread.hotkey_pressed
    -> Brain.on_listening_started          (state: LISTENING)
    -> VoiceThread.on_hotkey_pressed       (start recording)

  VoiceThread.transcript_ready
    -> Brain.on_thinking_started           (state: THINKING)
    -> AIThread.send_query

  AIThread.response_chunk
    -> UIManager.on_response_chunk         (streaming bubble update)

  AIThread.response_done
    -> Brain.on_talking_started            (state: TALKING, full text)
    -> TTSThread.speak

  TTSThread.speech_done
    -> Brain.on_ai_done                    (return to sensor-driven state)

  AIThread.error_occurred / VoiceThread.error_occurred
    -> UIManager.on_ai_error
    -> Brain.on_ai_done

Signal flow (always, regardless of ai_enabled):
  SystemMonitor.sensor_update -> Brain.on_sensor_update
  Brain.brain_output          -> UIManager.on_brain_output
  UIManager.animation_finished -> Brain.on_animation_done
"""

import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from brain import Brain
from config_manager import load_config
from system_monitor import SystemMonitor
from ui_manager import UIManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
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

    system_monitor.sensor_update.connect(brain.on_sensor_update)
    brain.brain_output.connect(ui.on_brain_output)
    ui.quit_requested.connect(app.quit)

    # Animation finished signal → Brain (handles INTRO→IDLE and ACTING→IDLE)
    ui.animation_finished.connect(brain.on_animation_done)

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
        ai_thread = AIThread(config)
        tts_thread = TTSThread(config)

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

        # AI response -> UI (streaming) + Brain (talking) + TTS
        ai_thread.response_chunk.connect(ui.on_response_chunk)
        ai_thread.response_done.connect(brain.on_talking_started)
        ai_thread.response_done.connect(tts_thread.speak)
        ai_thread.error_occurred.connect(ui.on_ai_error)
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
