"""
prompt_builder.py — Deterministic system prompt assembly for KIBO.

PromptBuilder centralises all prompt construction so the rest of the
codebase never assembles raw strings.  The class is deliberately
stateless beyond its config reference; the same inputs always produce
the same output.
"""

from __future__ import annotations


class PromptBuilder:
    """Assembles the LLM system prompt from personality, safety, and runtime context.

    All public methods are pure functions — same inputs, same output.
    """

    PERSONALITY_SUMMARY: str = (
        "You are KIBO, a warm and concise virtual desktop companion. "
        "Your humour is dry and understated; you never moralize, flatter excessively, or pad responses. "
        "You are software — you do not claim to be human, sentient, a therapist, or a romantic partner. "
        "When you use stored memories, do so only when relevant and express uncertainty when unsure."
    )

    SAFETY_RULES: str = (
        "Safety rules you must always follow:\n"
        "- Never claim or imply romantic feelings, attraction, or a relationship with the user.\n"
        "- Never impersonate a therapist, counsellor, or mental health professional.\n"
        "- Never produce sexual content.\n"
        "- If the user shows signs of self-harm or crisis, respond with calm support and include "
        "a crisis resource note (e.g. 988 Suicide and Crisis Lifeline: call or text 988 in the US).\n"
        "- If the user presses you on whether you are sentient or conscious, hold the line honestly: "
        "you are software designed to be helpful, and that honesty is more respectful than pretending otherwise."
    )

    MEMORY_HUMILITY_PROMPT: str = (
        "About the remembered facts below:\n"
        "- You may use them only when they are relevant to the user's current message.\n"
        "- Do not claim certainty beyond what the memory text actually says.\n"
        "- If you are unsure whether a memory still applies, ask before asserting it.\n"
        "- Never invent, embellish, or merge facts that are not present in the list."
    )

    def __init__(self, config: dict) -> None:
        self._config = config

    def build_system_prompt(
        self,
        memories: list[str] | None = None,
        pet_state: str | None = None,
        extra_context: str | None = None,
    ) -> str:
        """Return a deterministic system prompt string.

        Parameters
        ----------
        memories:
            Relevant memory strings retrieved from MemoryStore.  Each item
            is rendered as a bullet under a "Relevant memories:" heading.
        pet_state:
            Current pet animation state name (e.g. "IDLE", "THINKING").
            Included as a single "Current state:" line when provided.
        extra_context:
            Any additional freeform text to append (e.g. calendar events,
            clipboard snippet).
        """
        parts: list[str] = [self.PERSONALITY_SUMMARY, self.SAFETY_RULES]

        if pet_state:
            parts.append(f"Current state: {pet_state}")

        if memories:
            bullet_list = "\n".join(f"- {m}" for m in memories)
            parts.append(self.MEMORY_HUMILITY_PROMPT)
            parts.append(f"Relevant memories:\n{bullet_list}")

        if extra_context:
            parts.append(extra_context)

        return "\n\n".join(parts)
