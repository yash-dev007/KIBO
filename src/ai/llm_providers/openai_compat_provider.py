"""Generic OpenAI-compatible streaming provider.

Works with OpenRouter, NVIDIA NIM, and Google Gemini (via their OpenAI-compat
endpoints). Uses httpx for SSE streaming — no extra SDK required.
"""

from __future__ import annotations

import json
import logging
from typing import Iterator, Optional

import httpx

from .base import ChatChunk, ToolCall

logger = logging.getLogger(__name__)


class OpenAICompatProvider:
    """Streams chat from any OpenAI-API-compatible endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._extra_headers = extra_headers or {}

    def is_available(self) -> bool:
        return bool(self._api_key)

    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> Iterator[ChatChunk]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

        payload: dict = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": True,
            "temperature": 0.7,
            "max_tokens": 1024,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        tool_buffers: dict[int, dict] = {}

        try:
            with httpx.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self._timeout,
            ) as response:
                response.raise_for_status()

                for raw_line in response.iter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data: "):
                        continue

                    data = line[6:]
                    if data == "[DONE]":
                        break

                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue

                    choices = event.get("choices") or []
                    if not choices:
                        continue

                    delta = choices[0].get("delta") or {}

                    content = delta.get("content")
                    if content:
                        yield ChatChunk(text_delta=content)

                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        buf = tool_buffers.setdefault(idx, {"name": "", "args": ""})
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            buf["name"] = fn["name"]
                        if fn.get("arguments"):
                            buf["args"] += fn["arguments"]

        except httpx.HTTPStatusError as exc:
            logger.error("API error %s: %s", exc.response.status_code, exc.response.text)
            raise RuntimeError(
                f"API error {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except Exception as exc:
            logger.error("Request failed: %s", exc)
            raise

        for buf in tool_buffers.values():
            if not buf["name"]:
                continue
            try:
                args = json.loads(buf["args"]) if buf["args"] else {}
            except json.JSONDecodeError:
                continue
            yield ChatChunk(tool_call=ToolCall(name=buf["name"], arguments=args))

        yield ChatChunk(done=True)
