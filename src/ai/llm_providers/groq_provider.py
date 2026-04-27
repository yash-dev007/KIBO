"""Groq cloud provider — free-tier llama-3.3-70b at ~6000 tok/s.

Sub-300ms first token typical; uses official `groq` Python SDK which
is OpenAI-API-compatible.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Iterator, Optional

from .base import ChatChunk, ToolCall

logger = logging.getLogger(__name__)


class GroqProvider:
    def __init__(self, config: dict) -> None:
        from groq import Groq  # imported lazily; see __init__.py

        env_var = config.get("groq_api_key_env", "GROQ_API_KEY")
        api_key = os.environ.get(env_var)
        if not api_key:
            raise RuntimeError(f"{env_var} not set")

        self._client = Groq(api_key=api_key)
        self._model = config.get("groq_model", "llama-3.3-70b-versatile")
        self._timeout = float(config.get("groq_timeout_s", 30.0))

    def is_available(self) -> bool:
        # Constructor would have raised; reaching here means we have a key.
        return True

    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> Iterator[ChatChunk]:
        full_messages = [{"role": "system", "content": system}] + messages

        kwargs: dict = {
            "model": self._model,
            "messages": full_messages,
            "stream": True,
            "temperature": 0.7,
            "max_tokens": 512,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            stream = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.error("Groq request failed: %s", exc)
            raise

        # Tool-call accumulation (Groq streams tool args incrementally).
        tool_buffers: dict[int, dict] = {}

        for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta

            # 1. Text content stream
            if getattr(delta, "content", None):
                yield ChatChunk(text_delta=delta.content)

            # 2. Tool-call stream (incremental JSON args)
            tool_calls = getattr(delta, "tool_calls", None) or []
            for tc in tool_calls:
                idx = tc.index
                buf = tool_buffers.setdefault(idx, {"name": "", "args": ""})
                if tc.function and tc.function.name:
                    buf["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    buf["args"] += tc.function.arguments

        # Emit completed tool calls after stream closes.
        for buf in tool_buffers.values():
            if not buf["name"]:
                continue
            try:
                args = json.loads(buf["args"]) if buf["args"] else {}
            except json.JSONDecodeError:
                logger.warning("Groq tool-call args not valid JSON: %s", buf["args"])
                continue
            yield ChatChunk(tool_call=ToolCall(name=buf["name"], arguments=args))

        yield ChatChunk(done=True)
