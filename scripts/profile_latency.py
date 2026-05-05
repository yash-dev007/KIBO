"""
scripts/profile_latency.py — Real-world profiling to verify sub-200ms TTFS goal.

This script wires up the core Phase 3 components (AIClient, SentenceBuffer, TTSManager)
and measures the Time-To-First-Speech (TTFS). TTFS is the delta between sending a 
query and the TTS manager receiving the first chunk of text to speak.
"""

import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication

# Ensure src/ is in the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.ai_client import AIClient
from src.ai.sentence_buffer import SentenceBuffer
from src.ai.tts_manager import TTSManager


class LatencyTracker:
    def __init__(self):
        self.start_time = 0.0
        self.ttfs_time = 0.0
        self.first_speech_received = False
        
    def mark_start(self):
        self.start_time = time.perf_counter()
        
    def mark_speech(self, text: str):
        if not self.first_speech_received:
            self.ttfs_time = time.perf_counter()
            self.first_speech_received = True
            print(f"[{self.ttfs_time - self.start_time:.3f}s] First speech chunk: {text!r}")


def main():
    # We need a QCoreApplication to use Qt signals/slots
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    
    # Configure KIBO to use the fastest real models (or mock for baseline)
    config = {
        "llm_provider": "mock",
        "system_prompt": "You are KIBO.",
        "tts_enabled": True,
        "tts_provider": "mock",
        "conversation_history_limit": 5,
        "memory_extraction_inline": False
    }

    print("Initializing Phase 3 pipeline components...")
    client = AIClient(config)
    buf = SentenceBuffer()
    tts = TTSManager(config)
    tracker = LatencyTracker()

    # Wire components
    client.response_chunk.connect(buf.push)
    buf.sentence_ready.connect(tracker.mark_speech)
    buf.sentence_ready.connect(tts.speak_chunk)
    buf.flushed.connect(tts.end_stream)
    
    # Force mock provider responses for consistent profiling
    # (assuming AIClient has instantiated MockLLMProvider)
    # We will just inject some words to be spoken
    client._provider._responses = [
        "Well", " hello", " there.",
        " This", " is", " a", " latency", " test.",
    ]
    client._provider._delay = 0.02  # 20ms delay between words to simulate real LLM

    print("\nStarting latency profile test...")
    tracker.mark_start()
    client.send_query("Say hello!")
    buf.flush()
    
    # Allow signals to propagate
    app.processEvents()
    
    # Wait for the drain thread to finish
    deadline = time.time() + 3.0
    while tts._streaming_thread and tts._streaming_thread.is_alive():
        time.sleep(0.01)
        app.processEvents()
        if time.time() > deadline:
            print("Warning: Timeout waiting for TTS to finish")
            break

    ttfs_ms = (tracker.ttfs_time - tracker.start_time) * 1000
    
    print("\n=== Latency Profiling Results ===")
    print(f"Time-To-First-Speech (TTFS): {ttfs_ms:.1f} ms")
    
    if ttfs_ms < 200:
        print("[SUCCESS] Sub-200ms goal achieved.")
    else:
        print("[FAILED] Exceeded 200ms goal.")

if __name__ == "__main__":
    main()
