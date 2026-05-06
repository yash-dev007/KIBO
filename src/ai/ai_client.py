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
import json
import re
import threading
from typing import Optional

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QThread, Qt, Signal, Slot

from src.ai.llm_providers import LLMProvider, get_provider
from src.ai.llm_providers.base import REMEMBER_TOOL_SCHEMA
from src.ai.memory_store import MemoryStore
from src.ai.prompt_builder import PromptBuilder
from src.ai.safety import (
    SafetyCategory,
    check_assistant_response,
    check_user_input,
    crisis_response,
)

logger = logging.getLogger(__name__)


class AIClient(QObject):
    """Sends queries through an LLMProvider and streams back responses.

    Must be moved to a QThread before use.
    """

    response_chunk = Signal(str)         # text token delta
    response_done = Signal(str)          # full reply text
    memory_fact_extracted = Signal(dict) # one fact dict per `remember` tool call
    safety_event = Signal(str, str)      # (event_type, detail) — e.g. ("self_harm", "..."), ("response_flagged", "...")
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
        self._prompt_builder = PromptBuilder(config)
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

    # ------------------------------------------------------------------ #
    # Configuration and Slots
    # ------------------------------------------------------------------ #
    @Slot(dict)
    def on_config_changed(self, new_config: dict) -> None:
        self._config = new_config
        self._prompt_builder = PromptBuilder(new_config)
        self._history_limit = int(new_config.get("conversation_history_limit", 10))
        self._inline_memory = bool(new_config.get("memory_extraction_inline", True))
        
        try:
            self._provider = get_provider(new_config)
        except RuntimeError as exc:
            self._provider = None
            logger.error("No LLM provider available: %s", exc)

    def cancel_current(self) -> None:
        """Thread-safe: abort the in-flight stream."""
        self._cancel_event.set()

    @Slot(str)
    def send_query(self, user_text: str) -> None:
        """Slot: send user_text and stream the response."""
        if self._provider is None:
            try:
                self._provider = get_provider(self._config)
            except RuntimeError as exc:
                logger.debug("Provider retry failed: %s", exc)
                
        if self._provider is None:
            self.error_occurred.emit(
                "No LLM provider configured. Set GROQ_API_KEY or start Ollama."
            )
            return

        # Pre-LLM safety check: short-circuit on self-harm signals so the LLM
        # cannot accidentally minimize or moralize. KIBO replies with a calm,
        # resource-bearing message and skips the round-trip.
        user_safety = check_user_input(user_text)
        if user_safety.flagged:
            self.safety_event.emit(
                SafetyCategory.SELF_HARM.value, "User input flagged for self-harm signals"
            )
            self._history.append({"role": "user", "content": user_text})
            self._trim_history()
            crisis_text = crisis_response()
            self.response_chunk.emit(crisis_text)
            self._history.append({"role": "assistant", "content": crisis_text})
            self._trim_history()
            self.response_done.emit(crisis_text)
            return

        self._cancel_event.clear()
        self._history.append({"role": "user", "content": user_text})
        self._trim_history()

        raw_memory_context = (
            self._memory_store.build_memory_prompt(user_text)
            if self._memory_store
            else ""
        )
        memory_lines = (
            [raw_memory_context] if raw_memory_context else None
        )
        system = self._prompt_builder.build_system_prompt(memories=memory_lines)

        tools = (
            [REMEMBER_TOOL_SCHEMA]
            if self._inline_memory and _should_offer_memory_tool(user_text)
            else None
        )

        full_response = ""
        json_buffer = ""
        is_json_stream = False
        fact_extracted = False
        suppressed_tool_json = False
        
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
                    # Some local models print function-call JSON as text instead
                    # of using the tool channel. Buffer that candidate until the
                    # stream ends so it never leaks into chat bubbles.
                    if (
                        not full_response
                        and not json_buffer
                        and _looks_like_json_start(chunk.text_delta)
                    ):
                        is_json_stream = True
                        
                    if is_json_stream:
                        json_buffer += chunk.text_delta
                    else:
                        full_response += chunk.text_delta
                        self.response_chunk.emit(chunk.text_delta)

                if chunk.tool_call:
                    args = chunk.tool_call.arguments
                    if _valid_memory(args):
                        self.memory_fact_extracted.emit(args)
                        fact_extracted = True

                if chunk.done:
                    # Rescue hallucinated tool calls
                    if is_json_stream and json_buffer:
                        args, is_tool_json = _extract_memory_args_from_json(json_buffer)
                        if args is not None and _valid_memory(args):
                            self.memory_fact_extracted.emit(args)
                            fact_extracted = True
                        elif is_tool_json:
                            suppressed_tool_json = True
                        else:
                            full_response += json_buffer
                            self.response_chunk.emit(json_buffer)
                    break

        except Exception as exc:
            msg = f"LLM error: {exc}"
            logger.error(msg)
            self.error_occurred.emit(msg)
            return

        if fact_extracted:
            ack = "Got it! I've saved that to my memory."
            full_response += ack
            self.response_chunk.emit(ack)

        if not full_response and suppressed_tool_json:
            full_response = "Hi! How can I help?"
            self.response_chunk.emit(full_response)

        if full_response:
            # Post-LLM safety check: emit a structured warning event when the
            # reply contains prohibited claims/content. We do not mutate the
            # text — the prompt rules carry the load; this is a flag for
            # logging and any downstream UI.
            response_safety = check_assistant_response(full_response)
            if response_safety.flagged:
                category_value = (
                    response_safety.categories[0].value
                    if response_safety.categories
                    else "response_flagged"
                )
                self.safety_event.emit(category_value, response_safety.message)

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
    if not isinstance(args, dict):
        return False
        
    # Unnest if the LLM hallucinates `{"content": {"content": ...}}`
    if isinstance(args.get("content"), dict) and "content" in args["content"]:
        nested = args["content"]
        args["content"] = nested.get("content", "")
        args["category"] = nested.get("category", args.get("category"))
        args["keywords"] = nested.get("keywords", args.get("keywords", []))

    # Force types if the LLM hallucinates schema structures instead of values
    if isinstance(args.get("content"), dict):
        args["content"] = str(args.get("content", ""))
    if not isinstance(args.get("keywords"), list):
        args["keywords"] = []
    if not isinstance(args.get("category"), str):
        args["category"] = "fact"

    content_raw = args.get("content", "")
    content = content_raw.strip() if isinstance(content_raw, str) else ""
    if _is_low_value_memory(content):
        return False

    return (
        isinstance(args.get("content"), str)
        and len(content) > 0
    )


_MEMORY_CUE_PATTERN = re.compile(
    r"\b("
    r"remember|don't forget|do not forget|my name is|i am|i'm|i live|"
    r"i work|i study|i like|i love|i hate|i prefer|my favorite|"
    r"my favourite|call me|note that"
    r")\b",
    re.IGNORECASE,
)


def _should_offer_memory_tool(user_text: str) -> bool:
    """Only expose memory tools when the user likely shared durable context."""
    return bool(_MEMORY_CUE_PATTERN.search(user_text))


def _looks_like_json_start(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _extract_memory_args_from_json(text: str) -> tuple[Optional[dict], bool]:
    """Return memory args and whether the text was intended as tool-call JSON."""
    text_to_parse = text.strip()
    while text_to_parse:
        try:
            data = json.loads(text_to_parse)
            return _extract_memory_args(data)
        except json.JSONDecodeError:
            last_brace = text_to_parse.rfind("}", 0, len(text_to_parse) - 1)
            last_bracket = text_to_parse.rfind("]", 0, len(text_to_parse) - 1)
            last_end = max(last_brace, last_bracket)
            if last_end == -1:
                return None, False
            text_to_parse = text_to_parse[: last_end + 1]
    return None, False


def _extract_memory_args(data: object) -> tuple[Optional[dict], bool]:
    if isinstance(data, list):
        for item in data:
            args, is_tool_json = _extract_memory_args(item)
            if args is not None or is_tool_json:
                return args, is_tool_json
        return None, False

    if not isinstance(data, dict):
        return None, False

    name = str(data.get("name") or data.get("tool") or data.get("function") or "").lower()
    is_remember = name == "remember"
    if is_remember and ("parameters" in data or "arguments" in data):
        args = data.get("parameters") or data.get("arguments") or {}
        return (args if isinstance(args, dict) else None), True
    if is_remember:
        return data, True
    return None, False


def _is_low_value_memory(content: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", "", content.lower()).strip()
    return normalized in {
        "hi",
        "hello",
        "hey",
        "greeting",
        "user greeted",
        "user says hi",
        "user said hi",
        "user says hello",
        "user said hello",
    }


class AIThread(QThread):
    """Owns AIClient and runs a Qt event loop on this thread."""

    response_chunk = Signal(str)
    response_done = Signal(str)
    memory_fact_extracted = Signal(dict)
    safety_event = Signal(str, str)
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
        self._client.safety_event.connect(self.safety_event)
        self._client.error_occurred.connect(self.error_occurred)

    def run(self) -> None:
        self.exec()

    def send_query(self, text: str) -> None:
        QMetaObject.invokeMethod(
            self._client, "send_query", Qt.QueuedConnection, Q_ARG(str, text)
        )

    def cancel_current(self) -> None:
        self._client.cancel_current()

    @Slot(dict)
    def on_config_changed(self, new_config: dict) -> None:
        QMetaObject.invokeMethod(
            self._client, "on_config_changed", Qt.QueuedConnection, Q_ARG(dict, new_config)
        )

    def stop(self) -> None:
        self.cancel_current()
        self.quit()
        self.wait(3000)

    @property
    def client(self) -> AIClient:
        return self._client
