"""
ai_client.py — Provider-agnostic streaming chat client.

Picks the best LLM backend (Groq cloud > Ollama local) via
src.ai.llm_providers and streams response chunks to the UI on a QThread.

Memory facts arrive *inline* as `remember` tool calls during the same
streaming response — no second LLM round-trip. They're forwarded to
MemoryStore via the new memory_fact_extracted signal.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot

from src.ai.llm_providers import ChatChunk, LLMProvider, get_provider
from src.ai.llm_providers.base import REMEMBER_TOOL_SCHEMA
from src.ai.memory_store import MemoryStore

logger = logging.getLogger(__name__)


class AIClient(QObject):
    """Sends queries through an LLMProvider and streams back responses.

    Must be moved to a QThread before use.
    """

    response_chunk = Signal(str)         # text token delta
    response_done = Signal(str)          # full reply text
    memory_fact_extracted = Signal(dict) # one fact dict per `remember` tool call
    error_occurred = Signal(str)

    def __init__(
        self,
        config: dict,
        memory_store: Optional[MemoryStore] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._memory_store = memory_store
        self._history: list[dict] = []
        self._system_prompt = config.get(
            "system_prompt",
            "You are KIBO, a helpful desktop assistant.",
        )
        self._history_limit = int(config.get("conversation_history_limit", 10))
        self._cancel_event = threading.Event()

        self._provider: Optional[LLMProvider] = None
        try:
            self._provider = get_provider(config)
        except RuntimeError as exc:
            logger.error("No LLM provider available: %s", exc)

        self._inline_memory = bool(config.get("memory_extraction_inline", True))

    # ------------------------------------------------------------------ #
    # Compatibility shim — kept so existing callers don't break.
    # ------------------------------------------------------------------ #
    def check_ollama(self) -> bool:
        return self._provider is not None and self._provider.is_available()

    def cancel_current(self) -> None:
        """Thread-safe: abort the in-flight stream."""
        self._cancel_event.set()

    @Slot(str)
    def send_query(self, user_text: str) -> None:
        """Slot: send user_text and stream the response."""
        if self._provider is None:
            self.error_occurred.emit(
                "No LLM provider configured. Set GROQ_API_KEY or start Ollama."
            )
            return

        self._cancel_event.clear()
        self._history.append({"role": "user", "content": user_text})
        self._trim_history()

        memory_context = (
            self._memory_store.build_memory_prompt(user_text)
            if self._memory_store
            else ""
        )
        system = self._system_prompt
        if memory_context:
            system += "\n\nWhat you remember:\n" + memory_context

        tools = [REMEMBER_TOOL_SCHEMA] if self._inline_memory else None

        full_response = ""
        try:
            for chunk in self._provider.stream_chat(
                system=system, messages=list(self._history), tools=tools
            ):
                if self._cancel_event.is_set():
                    logger.info("Query cancelled — newer request pending")
                    if self._history and self._history[-1]["role"] == "user":
                        self._history.pop()
                    return

                if chunk.text_delta:
                    full_response += chunk.text_delta
                    self.response_chunk.emit(chunk.text_delta)

                if chunk.tool_call and chunk.tool_call.name == "remember":
                    args = chunk.tool_call.arguments
                    if _valid_memory(args):
                        self.memory_fact_extracted.emit(args)

                if chunk.done:
                    break

        except Exception as exc:
            msg = f"LLM error: {exc}"
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
        limit = self._history_limit * 2
        if len(self._history) > limit:
            self._history = self._history[-limit:]


def _valid_memory(args: dict) -> bool:
    return (
        isinstance(args, dict)
        and isinstance(args.get("content"), str)
        and len(args["content"].strip()) > 0
        and isinstance(args.get("keywords"), list)
    )


class AIThread(QThread):
    """Owns AIClient and runs a Qt event loop on this thread."""

    response_chunk = Signal(str)
    response_done = Signal(str)
    memory_fact_extracted = Signal(dict)
    error_occurred = Signal(str)

    def __init__(
        self,
        config: dict,
        memory_store: Optional[MemoryStore] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._client = AIClient(config, memory_store)
        self._client.moveToThread(self)
        self._client.response_chunk.connect(self.response_chunk)
        self._client.response_done.connect(self.response_done)
        self._client.memory_fact_extracted.connect(self.memory_fact_extracted)
        self._client.error_occurred.connect(self.error_occurred)

    def run(self) -> None:
        self.exec()

    def send_query(self, text: str) -> None:
        self._client.send_query(text)

    def cancel_current(self) -> None:
        self._client.cancel_current()

    def stop(self) -> None:
        self.quit()
        self.wait(3000)

    @property
    def client(self) -> AIClient:
        return self._client
