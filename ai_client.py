"""
ai_client.py — Ollama HTTP API wrapper with streaming support.

Runs on a QThread. Streams response tokens back via response_chunk signal,
then emits response_done when the full response is complete.

Conversation history is maintained as a list of {"role": ..., "content": ...}
dicts, capped at conversation_history_limit.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


class AIClient(QObject):
    """
    Sends queries to Ollama and streams back responses.
    Must be moved to a QThread before use.
    """

    response_chunk = Signal(str)   # emitted for each streamed token
    response_done = Signal(str)    # emitted once with full response text
    error_occurred = Signal(str)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._config = config
        self._history: list[dict] = []
        self._base_url = config.get("ollama_base_url", "http://localhost:11434")
        self._model = config.get("ollama_model", "qwen2.5-coder:7b")
        self._system_prompt = config.get("system_prompt", "You are KIBO, a helpful desktop assistant.")
        self._history_limit = int(config.get("conversation_history_limit", 10))

    def check_ollama(self) -> bool:
        """Returns True if Ollama is reachable."""
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    def send_query(self, user_text: str) -> None:
        """
        Slot: send user_text to Ollama and stream the response.
        Must be called on the thread this object lives on.
        """
        if not self.check_ollama():
            msg = "Can't reach my brain! Is Ollama running?"
            logger.warning(msg)
            self.error_occurred.emit(msg)
            return

        self._history.append({"role": "user", "content": user_text})
        self._trim_history()

        messages = [{"role": "system", "content": self._system_prompt}] + self._history

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
        }

        full_response = ""
        try:
            with httpx.Client(timeout=60.0) as client:
                with client.stream(
                    "POST",
                    f"{self._base_url}/api/chat",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            full_response += chunk
                            self.response_chunk.emit(chunk)

                        if data.get("done", False):
                            break

        except httpx.HTTPStatusError as exc:
            msg = f"Ollama returned {exc.response.status_code}"
            logger.error(msg)
            self.error_occurred.emit(msg)
            return
        except Exception as exc:
            msg = f"Ollama error: {exc}"
            logger.error(msg)
            self.error_occurred.emit(msg)
            return

        if full_response:
            self._history.append({"role": "assistant", "content": full_response})
            self._trim_history()
            self.response_done.emit(full_response)

    def clear_history(self) -> None:
        self._history = []

    def _trim_history(self) -> None:
        limit = self._history_limit * 2  # pairs of user+assistant
        if len(self._history) > limit:
            self._history = self._history[-limit:]


class AIThread(QThread):
    """Convenience wrapper: owns AIClient and runs Qt event loop on this thread."""

    response_chunk = Signal(str)
    response_done = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, config: dict, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._client = AIClient(config)
        self._client.moveToThread(self)
        self._client.response_chunk.connect(self.response_chunk)
        self._client.response_done.connect(self.response_done)
        self._client.error_occurred.connect(self.error_occurred)

    def run(self) -> None:
        self.exec()

    def send_query(self, text: str) -> None:
        # Called from main thread via queued connection
        self._client.send_query(text)

    def stop(self) -> None:
        self.quit()
        self.wait(3000)

    @property
    def client(self) -> AIClient:
        return self._client
