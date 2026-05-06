from __future__ import annotations

from src.ai.llm_providers import get_provider


def test_mock_provider_uses_configured_responses_and_delay() -> None:
    provider = get_provider(
        {
            "llm_provider": "mock",
            "demo_llm_responses": ["A", "B"],
            "demo_llm_delay_ms": 0,
        }
    )

    chunks = list(provider.stream_chat(system="", messages=[]))

    assert [c.text_delta for c in chunks if c.text_delta] == ["A", "B"]
    assert chunks[-1].done is True
    assert provider.is_available() is True
