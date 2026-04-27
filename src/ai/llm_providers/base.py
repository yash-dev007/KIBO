"""Protocol + DTOs for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional, Protocol


@dataclass(frozen=True)
class ToolCall:
    """A structured tool call emitted by the model."""

    name: str
    arguments: dict


@dataclass(frozen=True)
class ChatChunk:
    """One streaming event from the LLM.

    Either contains a text delta, a completed tool call, or marks the end.
    """

    text_delta: str = ""
    tool_call: Optional[ToolCall] = None
    done: bool = False


# Tool schema shared across providers. The model may optionally call
# `remember` zero or more times alongside its text reply.
REMEMBER_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "remember",
        "description": (
            "Save a durable factual memory about the user (preference, fact, "
            "person, location, task). Only call when something is genuinely "
            "worth remembering across conversations."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Single-sentence factual statement.",
                },
                "category": {
                    "type": "string",
                    "enum": ["preference", "fact", "person", "location", "task"],
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-6 lowercase keywords for retrieval.",
                },
            },
            "required": ["content", "category", "keywords"],
        },
    },
}


class LLMProvider(Protocol):
    """Common interface every LLM backend must implement."""

    def is_available(self) -> bool: ...

    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> Iterator[ChatChunk]:
        """Stream a chat response. Yields text deltas, then any tool calls,
        then a final ChatChunk(done=True). Must be re-entrant per call."""
        ...
