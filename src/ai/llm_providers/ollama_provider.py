"""Local Ollama provider — fallback when no Groq key.

Uses /api/chat streaming. Tool calls are best-effort: if the model and
runtime support them (llama 3.1+), we forward; otherwise text-only.
"""

from __future__ import annotations

import json
import logging
from typing import Iterator, Optional

import httpx

from .base import ChatChunk, ToolCall

logger = logging.getLogger(__name__)


class OllamaProvider:
    def __init__(self, config: dict) -> None:
        self._base_url = config.get("ollama_base_url", "http://localhost:11434")
        self._model = config.get("ollama_model", "llama3.2:3b")
        self._timeout = float(config.get("ollama_timeout_s", 60.0))

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> Iterator[ChatChunk]:
        payload: dict = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        try:
            with httpx.Client(timeout=self._timeout) as client:
                with client.stream("POST", f"{self._base_url}/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        msg = data.get("message", {})
                        chunk_text = msg.get("content", "")
                        if chunk_text:
                            yield ChatChunk(text_delta=chunk_text)

                        # Ollama emits tool_calls in the final message when supported
                        for tc in msg.get("tool_calls", []) or []:
                            fn = tc.get("function", {})
                            name = fn.get("name", "")
                            raw_args = fn.get("arguments", {})
                            args = (
                                raw_args
                                if isinstance(raw_args, dict)
                                else _safe_json(raw_args)
                            )
                            if name:
                                yield ChatChunk(tool_call=ToolCall(name=name, arguments=args))

                        if data.get("done", False):
                            break
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP %s", exc.response.status_code)
            raise
        except Exception as exc:
            logger.error("Ollama error: %s", exc)
            raise

        yield ChatChunk(done=True)


def _safe_json(value: object) -> dict:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
