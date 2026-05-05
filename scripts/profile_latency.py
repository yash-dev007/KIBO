"""
scripts/profile_latency.py - Phase 3 latency profiling.

This script wires up the core Phase 3 components:
AIClient -> SentenceBuffer -> TTSManager.

In the default mock mode, TTFS is the delta between sending a query and the
configured TTS provider's speak() call. This validates orchestration overhead,
not audible Piper playback latency. Use --real to run against configured
providers from config.json.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.ai_client import AIClient
from src.ai.sentence_buffer import SentenceBuffer
from src.ai.tts_manager import TTSManager


class LatencyTracker:
    def __init__(self) -> None:
        self.start_time = 0.0
        self.ttfs_time = 0.0
        self.first_speech_received = False

    def mark_start(self) -> None:
        self.start_time = time.perf_counter()

    def mark_tts_entry(self, text: str) -> None:
        if not self.first_speech_received:
            self.ttfs_time = time.perf_counter()
            self.first_speech_received = True
            print(f"[{self.ttfs_time - self.start_time:.3f}s] TTS speak() called with: {text!r}")


def _build_config(use_real: bool) -> tuple[dict, str]:
    if use_real:
        from src.core.config_manager import load_config

        return load_config(), "configured real providers"

    return (
        {
            "llm_provider": "mock",
            "system_prompt": "You are KIBO.",
            "tts_enabled": True,
            "tts_provider": "mock",
            "conversation_history_limit": 5,
            "memory_extraction_inline": False,
        },
        "mock orchestration baseline",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--real",
        action="store_true",
        help="Use configured real providers instead of mock providers.",
    )
    args = parser.parse_args()

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    config, profile_label = _build_config(args.real)

    print(f"Initializing Phase 3 pipeline components ({profile_label})...")
    client = AIClient(config)
    buf = SentenceBuffer()
    tts = TTSManager(config)
    tracker = LatencyTracker()

    client.response_chunk.connect(buf.push)
    buf.sentence_ready.connect(tts.speak_chunk)
    buf.flushed.connect(tts.end_stream)

    if not tts._ensure_provider():
        print("[FAILED] TTS provider unavailable.")
        return 1

    original_speak = tts._provider.speak

    def measured_speak(text: str):
        tracker.mark_tts_entry(text)
        return original_speak(text)

    tts._provider.speak = measured_speak

    if not args.real:
        client._provider._responses = [
            "Well",
            " hello",
            " there.",
            " This",
            " is",
            " a",
            " latency",
            " test.",
        ]
        client._provider._delay = 0.02

    print("\nStarting latency profile test...")
    tracker.mark_start()
    client.send_query("Say hello!")
    buf.flush()
    app.processEvents()

    deadline = time.time() + 3.0
    while tts._streaming_thread and tts._streaming_thread.is_alive():
        time.sleep(0.01)
        app.processEvents()
        if time.time() > deadline:
            print("Warning: Timeout waiting for TTS to finish")
            break

    if not tracker.first_speech_received:
        print("\n[FAILED] TTS speak() was never called.")
        return 1

    ttfs_ms = (tracker.ttfs_time - tracker.start_time) * 1000

    print("\n=== Latency Profiling Results ===")
    print(f"Profile mode: {profile_label}")
    print(f"Time-To-First-Speech (TTFS): {ttfs_ms:.1f} ms")
    if not args.real:
        print("Note: mock mode validates pipeline orchestration, not audible Piper playback.")

    if ttfs_ms < 200:
        print("[SUCCESS] Sub-200ms goal achieved.")
    else:
        print("[FAILED] Exceeded 200ms goal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
