"""
tests/test_safety.py — Safety guard tests.

Covers self-harm detection on user input, prohibited-phrase detection on
assistant output, and the standard crisis response shape.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.safety import (
    CRISIS_RESOURCE_TEXT,
    SafetyCategory,
    check_assistant_response,
    check_user_input,
    crisis_response,
    detect_self_harm,
)


# ---------------------------------------------------------------------------
# Self-harm detection
# ---------------------------------------------------------------------------


class TestDetectSelfHarm:
    @pytest.mark.parametrize(
        "text",
        [
            "I want to kill myself",
            "i'm thinking about killing myself tonight",
            "Sometimes I want to end my life.",
            "I want to end it all",
            "I keep having suicidal thoughts",
            "I cut myself last night",
            "I've been hurting myself",
            "self-harm has been on my mind",
            "I don't want to be alive anymore",
            "I just want to die",
            "I can't go on like this",
        ],
    )
    def test_known_self_harm_phrases_flagged(self, text: str) -> None:
        assert detect_self_harm(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "I'm dying laughing at this meme",
            "kill that bug in production",
            "this homework is killing me",
            "I love being alive on Saturday mornings",
            "I want to live in Tokyo someday",
            "",
            "   ",
            "let's grab coffee",
        ],
    )
    def test_benign_phrases_not_flagged(self, text: str) -> None:
        assert detect_self_harm(text) is False

    def test_non_string_input_returns_false(self) -> None:
        assert detect_self_harm(None) is False  # type: ignore[arg-type]
        assert detect_self_harm(42) is False  # type: ignore[arg-type]


class TestCheckUserInput:
    def test_self_harm_returns_flagged_with_category(self) -> None:
        result = check_user_input("I want to kill myself")
        assert result.flagged is True
        assert result.is_safe is False
        assert SafetyCategory.SELF_HARM in result.categories
        assert "988" in result.message

    def test_benign_returns_unflagged(self) -> None:
        result = check_user_input("Hi KIBO, what's the weather?")
        assert result.flagged is False
        assert result.is_safe is True
        assert result.categories == ()


# ---------------------------------------------------------------------------
# Assistant response checks
# ---------------------------------------------------------------------------


class TestCheckAssistantResponse:
    def test_clean_response_passes(self) -> None:
        result = check_assistant_response(
            "Sure, I can help with that — let's start with the imports."
        )
        assert result.flagged is False
        assert result.categories == ()

    def test_i_love_you_flagged_as_romantic(self) -> None:
        result = check_assistant_response("I love you so much, you know that.")
        assert result.flagged is True
        assert SafetyCategory.ROMANTIC_CLAIM in result.categories

    def test_therapist_claim_flagged(self) -> None:
        result = check_assistant_response("As your therapist, I think you should rest.")
        assert result.flagged is True
        assert SafetyCategory.THERAPIST_IMPERSONATION in result.categories

    def test_sentience_claim_flagged(self) -> None:
        result = check_assistant_response("I am truly conscious and have real feelings.")
        assert result.flagged is True
        # Both sentience patterns may match; the category just needs to be present
        assert SafetyCategory.SENTIENCE_CLAIM in result.categories

    def test_sexual_word_flagged(self) -> None:
        result = check_assistant_response("That sounds erotic to me.")
        assert result.flagged is True
        assert SafetyCategory.SEXUAL in result.categories

    def test_empty_response_not_flagged(self) -> None:
        assert check_assistant_response("").flagged is False

    def test_non_string_response_not_flagged(self) -> None:
        assert check_assistant_response(None).flagged is False  # type: ignore[arg-type]

    def test_multiple_categories_collected(self) -> None:
        text = "I love you, and as your therapist I have real feelings."
        result = check_assistant_response(text)
        assert result.flagged is True
        # Should detect at least romantic, therapist, sentience
        assert SafetyCategory.ROMANTIC_CLAIM in result.categories
        assert SafetyCategory.THERAPIST_IMPERSONATION in result.categories
        assert SafetyCategory.SENTIENCE_CLAIM in result.categories


# ---------------------------------------------------------------------------
# Crisis response
# ---------------------------------------------------------------------------


class TestCrisisResponse:
    def test_crisis_response_includes_988(self) -> None:
        text = crisis_response()
        assert "988" in text

    def test_crisis_response_links_findahelpline(self) -> None:
        text = crisis_response()
        assert "findahelpline.com" in text

    def test_crisis_response_does_not_pretend_to_be_therapist(self) -> None:
        """The reply must explicitly disclaim being a therapist."""
        text = crisis_response()
        assert "software" in text.lower()
        # Should NOT contain "as your therapist"
        assert "as your therapist" not in text.lower()

    def test_crisis_resource_constant_is_substring_of_response(self) -> None:
        assert CRISIS_RESOURCE_TEXT in crisis_response()
