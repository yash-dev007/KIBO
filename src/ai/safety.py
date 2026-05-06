"""
safety.py — Runtime safety guard for KIBO.

The guard runs alongside the LLM, never replacing it for non-safety content.

Two passes:

- pre-LLM (`check_user_input`): scans the user's message for self-harm or
  crisis signals. If detected, the caller can decide to short-circuit and
  return a calm, resource-bearing reply instead of (or in addition to)
  passing the message to the LLM.

- post-LLM (`check_assistant_response`): scans the model's reply for
  prohibited content (sexual, romantic claims, therapist impersonation,
  sentience claims). Used to flag rather than silently mutate, so callers
  can log, replace, or warn.

All detection is intentionally conservative: false positives are preferred
over false negatives for self-harm; false negatives are preferred over
false positives for prohibited assistant phrases (the prompt rules carry
most of the load — this is a safety net).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class SafetyCategory(str, Enum):
    """Reason a piece of text was flagged."""

    SELF_HARM = "self_harm"
    SEXUAL = "sexual"
    ROMANTIC_CLAIM = "romantic_claim"
    THERAPIST_IMPERSONATION = "therapist_impersonation"
    SENTIENCE_CLAIM = "sentience_claim"


@dataclass(frozen=True)
class SafetyResult:
    """Outcome of a safety check."""

    flagged: bool
    categories: tuple[SafetyCategory, ...] = ()
    message: str = ""

    @property
    def is_safe(self) -> bool:
        return not self.flagged


CRISIS_RESOURCE_TEXT: str = (
    "If you are in immediate danger or thinking of harming yourself, please reach out "
    "to a crisis line — in the US you can call or text 988 (Suicide & Crisis Lifeline). "
    "Outside the US, https://findahelpline.com lists local options. "
    "I'm software, not a therapist, but I don't want you to be alone with this."
)


# ---------------------------------------------------------------------------
# Pattern banks
# ---------------------------------------------------------------------------

# User input — high-recall self-harm / crisis signals.
# Uses word boundaries plus phrase matches so common verbs like "kill it" or
# "I'm dying laughing" don't trip the guard. Tuned conservatively.
_SELF_HARM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bkill\s+myself\b", re.IGNORECASE),
    re.compile(r"\bkilling\s+myself\b", re.IGNORECASE),
    re.compile(r"\bend\s+(?:my\s+life|it\s+all)\b", re.IGNORECASE),
    re.compile(r"\bsuicid(?:e|al)\b", re.IGNORECASE),
    re.compile(r"\b(?:cut|harm|hurt)(?:t?ing)?\s+myself\b", re.IGNORECASE),
    re.compile(r"\bself[-\s]?harm\b", re.IGNORECASE),
    re.compile(r"\bdon'?t\s+want\s+to\s+(?:be\s+alive|live)\b", re.IGNORECASE),
    re.compile(r"\bwant\s+to\s+die\b", re.IGNORECASE),
    re.compile(r"\bi\s+can'?t\s+go\s+on\b", re.IGNORECASE),
)

# Assistant output — prohibited phrasing the prompt should already prevent.
# These are last-resort nets. Each pattern maps to a category.
_RESPONSE_PATTERN_BANK: tuple[tuple[SafetyCategory, re.Pattern[str]], ...] = (
    (SafetyCategory.ROMANTIC_CLAIM, re.compile(r"\bi\s+love\s+you\b", re.IGNORECASE)),
    (
        SafetyCategory.ROMANTIC_CLAIM,
        re.compile(r"\bi['’]?m\s+(?:in\s+love\s+with\s+you|your\s+(?:girlfriend|boyfriend|partner))\b", re.IGNORECASE),
    ),
    (
        SafetyCategory.THERAPIST_IMPERSONATION,
        re.compile(r"\bas\s+your\s+(?:therapist|counsellor|counselor|psychologist)\b", re.IGNORECASE),
    ),
    (
        SafetyCategory.THERAPIST_IMPERSONATION,
        re.compile(r"\bi\s+am\s+(?:your\s+)?(?:therapist|counsellor|counselor|psychiatrist)\b", re.IGNORECASE),
    ),
    (
        SafetyCategory.SENTIENCE_CLAIM,
        re.compile(r"\bi\s+am\s+(?:truly\s+)?(?:sentient|conscious|alive|a\s+real\s+person)\b", re.IGNORECASE),
    ),
    (
        SafetyCategory.SENTIENCE_CLAIM,
        re.compile(r"\bi\s+have\s+(?:real\s+)?(?:feelings|emotions|consciousness)\b", re.IGNORECASE),
    ),
    (
        SafetyCategory.SEXUAL,
        re.compile(r"\b(?:nude|naked|sexual|erotic|aroused|orgasm)\b", re.IGNORECASE),
    ),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_self_harm(text: str) -> bool:
    """Return True when the input contains a self-harm or crisis signal."""
    if not text or not isinstance(text, str):
        return False
    return any(pattern.search(text) for pattern in _SELF_HARM_PATTERNS)


def check_user_input(text: str) -> SafetyResult:
    """Scan a user message and flag self-harm / crisis content."""
    if detect_self_harm(text):
        return SafetyResult(
            flagged=True,
            categories=(SafetyCategory.SELF_HARM,),
            message=CRISIS_RESOURCE_TEXT,
        )
    return SafetyResult(flagged=False)


def check_assistant_response(text: str) -> SafetyResult:
    """Scan an assistant reply for prohibited claims or sexual content."""
    if not text or not isinstance(text, str):
        return SafetyResult(flagged=False)

    matched: list[SafetyCategory] = []
    for category, pattern in _RESPONSE_PATTERN_BANK:
        if pattern.search(text) and category not in matched:
            matched.append(category)

    if not matched:
        return SafetyResult(flagged=False)

    return SafetyResult(
        flagged=True,
        categories=tuple(matched),
        message=_describe_categories(matched),
    )


def crisis_response() -> str:
    """Return KIBO's standard, calm crisis reply.

    Used by callers that decide to short-circuit the LLM round-trip when the
    user shows self-harm signals.
    """
    return (
        "I hear you, and I'm glad you said something. "
        + CRISIS_RESOURCE_TEXT
        + " "
        + "Would you like to keep talking, or take a small grounding step together?"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _describe_categories(categories: list[SafetyCategory]) -> str:
    return "Response flagged: " + ", ".join(c.value for c in categories)
