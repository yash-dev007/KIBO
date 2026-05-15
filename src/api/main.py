"""
src/api/main.py — Pure-Python headless backend composition root.

Creates all backend components, wires them via EventBus, then starts
the FastAPI server with uvicorn. No Qt dependency.

Usage:
    python -m src.api.main               # default port 8765
    python -m src.api.main --port 9000
"""

from __future__ import annotations

import argparse
import logging
import re
import signal
import sys
from typing import Optional

from src.api.event_bus import EventBus
from src.api.server import create_app
from src.core.config_manager import FileConfigManager, get_user_data_dir, load_config

logger = logging.getLogger(__name__)


def _sanitize_text(text: str) -> str:
    cleaned = re.sub(r"\(\s*\*.*?\*\s*\)", " ", text, flags=re.DOTALL)
    cleaned = re.sub(r"\*[^*\n]{1,120}\*", " ", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip() or text.strip()


def create_backend(config: dict) -> dict:
    """Construct and wire all backend components. Returns a component dict."""

    bus = EventBus()
    config_manager = FileConfigManager()

    from src.ai.conversation_store import ConversationStore
    conversation_store = ConversationStore(get_user_data_dir())

    # ── Core components ───────────────────────────────────────────────────
    from src.ai.brain import Brain
    from src.ai.memory_store import MemoryStore
    from src.system.calendar_manager import CalendarManager
    from src.system.notification_router import NotificationRouter
    from src.system.proactive_engine import ProactiveEngine
    from src.system.system_monitor import SystemMonitor
    from src.system.task_runner import TaskRunner

    notification_router = NotificationRouter(config, event_bus=bus)
    memory_store = MemoryStore(config, event_bus=bus)
    brain = Brain(config, router=notification_router, event_bus=bus)
    system_monitor = SystemMonitor(config, event_bus=bus)
    proactive_engine = ProactiveEngine(config, router=notification_router, event_bus=bus)
    calendar_manager = CalendarManager(config, event_bus=bus)
    task_runner = TaskRunner(config, MagicClient(), event_bus=bus)

    # ── Core wiring ───────────────────────────────────────────────────────
    bus.on("sensor_update", brain.on_sensor_update)
    bus.on("sensor_update", proactive_engine.on_sensor_update)
    bus.on("events_updated", proactive_engine.on_calendar_updated)
    bus.on("task_completed", proactive_engine.on_task_completed)
    bus.on("task_blocked", proactive_engine.on_task_blocked)
    bus.on("memory_fact_extracted", memory_store.add_fact_inline)

    # Config updates
    bus.on("config_changed", brain.on_config_changed)
    bus.on("config_changed", system_monitor.on_config_changed)
    bus.on("config_changed", proactive_engine.on_config_changed)
    bus.on("config_changed", notification_router.on_config_changed)
    bus.on("config_changed", memory_store.on_config_changed)

    # ── AI wiring (when enabled) ──────────────────────────────────────────
    ai_thread = None
    tts_thread = None
    voice_thread = None
    hotkey_thread = None
    sentence_buffer = None

    if config.get("ai_enabled", True):
        from src.ai.ai_client import AIThread
        from src.ai.sentence_buffer import SentenceBuffer
        from src.ai.tts_manager import TTSThread
        from src.ai.voice_listener import VoiceThread
        from src.system.hotkey_listener import HotkeyThread

        ai_thread = AIThread(config, memory_store=memory_store, event_bus=bus)
        tts_thread = TTSThread(config, event_bus=bus)
        voice_thread = VoiceThread(config, event_bus=bus)
        hotkey_thread = HotkeyThread(config, event_bus=bus)
        sentence_buffer = SentenceBuffer(event_bus=bus)

        # Config updates for AI components
        bus.on("config_changed", ai_thread.on_config_changed)
        bus.on("config_changed", lambda cfg: tts_thread.manager.set_enabled(cfg.get("tts_enabled", True)))

        # Hotkey → brain + voice
        bus.on("hotkey_pressed", brain.on_listening_started)
        bus.on("hotkey_pressed", voice_thread.on_hotkey_pressed)

        # Voice transcript → AI
        bus.on("transcript_ready", lambda text: ai_thread.send_query(text))
        bus.on("error_occurred", lambda _: brain.on_ai_done())

        # AI chunks → sentence buffer → TTS
        bus.on("response_chunk", sentence_buffer.push)
        bus.on("sentence_ready", tts_thread.speak_chunk)
        bus.on("flushed", lambda: tts_thread.end_stream())

        def _on_response_done(text: str) -> None:
            clean = _sanitize_text(text)
            brain.on_talking_started(clean)
            sentence_buffer.flush()

        bus.on("response_done", _on_response_done)
        bus.on("speech_done", brain.on_ai_done)

        # Re-wire task_runner with real AI client
        task_runner = TaskRunner(config, ai_thread.client, event_bus=bus)

    return {
        "event_bus": bus,
        "brain": brain,
        "memory_store": memory_store,
        "conversation_store": conversation_store,
        "system_monitor": system_monitor,
        "proactive_engine": proactive_engine,
        "notification_router": notification_router,
        "calendar_manager": calendar_manager,
        "task_runner": task_runner,
        "ai_thread": ai_thread,
        "tts_thread": tts_thread,
        "voice_thread": voice_thread,
        "hotkey_thread": hotkey_thread,
        "sentence_buffer": sentence_buffer,
        "config_manager": config_manager,
    }


class MagicClient:
    """Stub AI client for when ai_enabled=False."""
    pass


def start(config: dict, host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    components = create_backend(config)
    bus: EventBus = components["event_bus"]

    app = create_app(
        bus,
        config_manager=components["config_manager"],
        memory_store=components["memory_store"],
        task_runner=components["task_runner"],
        ai_thread=components["ai_thread"],
        conversation_store=components["conversation_store"],
    )

    # Start all background components
    components["system_monitor"].start()
    components["calendar_manager"].start()
    components["proactive_engine"].start()

    if components["ai_thread"]:
        components["ai_thread"].start()
    if components["tts_thread"]:
        components["tts_thread"].start()
    if components["voice_thread"]:
        components["voice_thread"].start()
    if components["hotkey_thread"]:
        components["hotkey_thread"].start()
    if components["task_runner"]:
        components["task_runner"].start()

    def _shutdown(sig, frame):
        logger.info("Shutting down KIBO backend…")
        components["system_monitor"].stop()
        components["calendar_manager"].stop()
        components["proactive_engine"].stop()
        if components["ai_thread"]:
            components["ai_thread"].stop()
        if components["tts_thread"]:
            components["tts_thread"].stop()
        if components["task_runner"]:
            components["task_runner"].stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("KIBO API server starting on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="KIBO headless backend server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    config_manager = FileConfigManager()
    start(config_manager.get_config(), host=args.host, port=args.port)
