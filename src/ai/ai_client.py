"""
ai_client.py — Provider-agnostic streaming chat client.

Picks the best LLM backend (Groq cloud > Ollama local) via
src.ai.llm_providers and streams response chunks via EventBus.

Memory facts arrive *inline* as `remember` tool calls during the same
streaming response — no second LLM round-trip. They're forwarded to
MemoryStore via the memory_fact_extracted event.
"""

from __future__ import annotations

import logging
import json
import queue
import re
import threading
from typing import Optional

from src.ai.llm_providers import LLMProvider, get_provider
from src.ai.llm_providers.base import REMEMBER_TOOL_SCHEMA
from src.ai.memory_store import MemoryStore
from src.ai.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class AIClient:
    """Sends queries through an LLMProvider and streams back responses via EventBus."""

    def __init__(
        self,
        config: dict,
        memory_store: Optional[MemoryStore] = None,
        event_bus=None,
    ) -> None:
        self._config = config
        self._event_bus = event_bus
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

    def check_ollama(self) -> bool:
        return self._provider is not None and self._provider.is_available()

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
        self._cancel_event.set()

    def send_query(self, user_text: str) -> None:
        if self._provider is None:
            try:
                self._provider = get_provider(self._config)
            except RuntimeError as exc:
                logger.debug("Provider retry failed: %s", exc)

        if self._provider is None:
            if self._event_bus:
                self._event_bus.emit(
                    "error_occurred",
                    "No LLM provider configured. Set GROQ_API_KEY or start Ollama.",
                )
            return

        self._cancel_event.clear()
        self._history.append({"role": "user", "content": user_text})
        self._trim_history()

        raw_memory_context = (
            self._memory_store.build_memory_prompt(user_text)
            if self._memory_store
            else ""
        )
        memory_lines = [raw_memory_context] if raw_memory_context else None
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
                        if self._event_bus:
                            self._event_bus.emit("response_chunk", chunk.text_delta)

                if chunk.tool_call:
                    args = chunk.tool_call.arguments
                    if _valid_memory(args):
                        if self._event_bus:
                            self._event_bus.emit("memory_fact_extracted", args)
                        fact_extracted = True

                if chunk.done:
                    if is_json_stream and json_buffer:
                        args, is_tool_json = _extract_memory_args_from_json(json_buffer)
                        if args is not None and _valid_memory(args):
                            if self._event_bus:
                                self._event_bus.emit("memory_fact_extracted", args)
                            fact_extracted = True
                        elif is_tool_json:
                            suppressed_tool_json = True
                        else:
                            full_response += json_buffer
                            if self._event_bus:
                                self._event_bus.emit("response_chunk", json_buffer)
                    break

        except Exception as exc:
            msg = f"LLM error: {exc}"
            logger.error(msg)
            if self._event_bus:
                self._event_bus.emit("error_occurred", msg)
            return

        if fact_extracted:
            ack = "Got it! I've saved that to my memory."
            full_response += ack
            if self._event_bus:
                self._event_bus.emit("response_chunk", ack)

        if not full_response and suppressed_tool_json:
            full_response = "Hi! How can I help?"
            if self._event_bus:
                self._event_bus.emit("response_chunk", full_response)

        if full_response:
            self._history.append({"role": "assistant", "content": full_response})
            self._trim_history()
            if self._event_bus:
                self._event_bus.emit("response_done", full_response)

    def clear_history(self) -> None:
        self._history = []

    def _trim_history(self) -> None:
        limit = self._history_limit * 2
        if len(self._history) > limit:
            self._history = self._history[-limit:]


def _valid_memory(args: dict) -> bool:
    if not isinstance(args, dict):
        return False

    if isinstance(args.get("content"), dict) and "content" in args["content"]:
        nested = args["content"]
        args["content"] = nested.get("content", "")
        args["category"] = nested.get("category", args.get("category"))
        args["keywords"] = nested.get("keywords", args.get("keywords", []))

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

    return isinstance(args.get("content"), str) and len(content) > 0


_MEMORY_CUE_PATTERN = re.compile(
    r"\b("
    r"remember|don't forget|do not forget|my name is|i am|i'm|i live|"
    r"i work|i study|i like|i love|i hate|i prefer|my favorite|"
    r"my favourite|call me|note that"
    r")\b",
    re.IGNORECASE,
)


def _should_offer_memory_tool(user_text: str) -> bool:
    return bool(_MEMORY_CUE_PATTERN.search(user_text))


def _looks_like_json_start(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _extract_memory_args_from_json(text: str) -> tuple[Optional[dict], bool]:
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
        "hi", "hello", "hey", "greeting",
        "user greeted", "user says hi", "user said hi",
        "user says hello", "user said hello",
    }


class AIThread(threading.Thread):
    """Daemon thread that owns an AIClient and dispatches calls via a queue."""

    def __init__(
        self,
        config: dict,
        memory_store: Optional[MemoryStore] = None,
        event_bus=None,
    ) -> None:
        super().__init__(daemon=True)
        self._client = AIClient(config, memory_store, event_bus=event_bus)
        self._queue: queue.Queue[Optional[tuple]] = queue.Queue()
        self._stop_event = threading.Event()

    @property
    def client(self) -> AIClient:
        return self._client

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.1)
                try:
                    if item is None:
                        break
                    method, arg = item
                    if arg is None:
                        getattr(self._client, method)()
                    else:
                        getattr(self._client, method)(arg)
                finally:
                    self._queue.task_done()
            except queue.Empty:
                continue

    def send_query(self, text: str) -> None:
        self._queue.put(("send_query", text))

    def cancel_current(self) -> None:
        self._client.cancel_current()

    def on_config_changed(self, new_config: dict) -> None:
        self._queue.put(("on_config_changed", new_config))

    def stop(self) -> None:
        self.cancel_current()
        self._stop_event.set()
