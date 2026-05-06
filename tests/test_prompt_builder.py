"""
tests/test_prompt_builder.py — Snapshot and property tests for PromptBuilder.
"""

from __future__ import annotations

import pytest

from src.ai.prompt_builder import PromptBuilder


@pytest.fixture()
def builder() -> PromptBuilder:
    return PromptBuilder(config={"personality_version": "1.0", "safety_version": "1.0"})


def test_system_prompt_contains_personality(builder: PromptBuilder) -> None:
    result = builder.build_system_prompt()
    assert PromptBuilder.PERSONALITY_SUMMARY in result


def test_system_prompt_contains_safety_rules(builder: PromptBuilder) -> None:
    result = builder.build_system_prompt()
    assert PromptBuilder.SAFETY_RULES in result


def test_system_prompt_with_memories(builder: PromptBuilder) -> None:
    memories = ["user's name is Alex", "user prefers Python"]
    result = builder.build_system_prompt(memories=memories)
    assert "user's name is Alex" in result
    assert "user prefers Python" in result
    assert "Relevant memories:" in result


def test_system_prompt_with_pet_state(builder: PromptBuilder) -> None:
    result = builder.build_system_prompt(pet_state="THINKING")
    assert "Current state: THINKING" in result


def test_system_prompt_is_deterministic(builder: PromptBuilder) -> None:
    memories = ["prefers dark mode"]
    result1 = builder.build_system_prompt(memories=memories, pet_state="IDLE", extra_context="it is Tuesday")
    result2 = builder.build_system_prompt(memories=memories, pet_state="IDLE", extra_context="it is Tuesday")
    assert result1 == result2


def test_system_prompt_no_memories(builder: PromptBuilder) -> None:
    # Must not raise and must not include the memories heading
    result = builder.build_system_prompt(memories=None)
    assert "Relevant memories:" not in result
    assert PromptBuilder.PERSONALITY_SUMMARY in result


def test_system_prompt_empty_memories_list(builder: PromptBuilder) -> None:
    # An empty list is falsy; memories heading must be omitted
    result = builder.build_system_prompt(memories=[])
    assert "Relevant memories:" not in result


def test_system_prompt_with_extra_context(builder: PromptBuilder) -> None:
    result = builder.build_system_prompt(extra_context="User has a meeting at 3pm.")
    assert "User has a meeting at 3pm." in result


def test_system_prompt_section_order(builder: PromptBuilder) -> None:
    # Personality comes before safety, state before memories
    result = builder.build_system_prompt(
        memories=["likes coffee"], pet_state="HAPPY"
    )
    personality_pos = result.index(PromptBuilder.PERSONALITY_SUMMARY)
    safety_pos = result.index("Safety rules")
    state_pos = result.index("Current state: HAPPY")
    memory_pos = result.index("Relevant memories:")
    assert personality_pos < safety_pos < state_pos < memory_pos


# ---------------------------------------------------------------------------
# Phase 3 — Memory recall humility nudges
# ---------------------------------------------------------------------------


def test_humility_prompt_present_when_memories_provided(builder: PromptBuilder) -> None:
    result = builder.build_system_prompt(memories=["user prefers Python"])
    assert PromptBuilder.MEMORY_HUMILITY_PROMPT in result


def test_humility_prompt_absent_without_memories(builder: PromptBuilder) -> None:
    result = builder.build_system_prompt(memories=None)
    assert PromptBuilder.MEMORY_HUMILITY_PROMPT not in result


def test_humility_prompt_absent_with_empty_memory_list(builder: PromptBuilder) -> None:
    result = builder.build_system_prompt(memories=[])
    assert PromptBuilder.MEMORY_HUMILITY_PROMPT not in result


def test_humility_prompt_appears_before_memory_bullets(builder: PromptBuilder) -> None:
    result = builder.build_system_prompt(memories=["user lives in Tokyo"])
    humility_pos = result.index(PromptBuilder.MEMORY_HUMILITY_PROMPT)
    bullet_pos = result.index("Relevant memories:")
    assert humility_pos < bullet_pos


def test_humility_prompt_warns_against_invention(builder: PromptBuilder) -> None:
    """The humility text must explicitly forbid inventing memories."""
    text = PromptBuilder.MEMORY_HUMILITY_PROMPT.lower()
    assert "invent" in text or "embellish" in text


def test_humility_prompt_warns_against_overcertainty(builder: PromptBuilder) -> None:
    text = PromptBuilder.MEMORY_HUMILITY_PROMPT.lower()
    assert "certainty" in text or "unsure" in text or "ask" in text
