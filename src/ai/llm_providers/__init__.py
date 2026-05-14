"""LLM provider abstraction.

Selects the backend based on config `llm_provider`:
  "auto"        → Groq (if key present) → Ollama (if reachable)
  "groq"        → Groq cloud
  "openrouter"  → OpenRouter (OpenAI-compatible)
  "nvidia"      → NVIDIA NIM (OpenAI-compatible)
  "google"      → Google Gemini (OpenAI-compatible endpoint)
  "ollama"      → Local Ollama
  "mock"        → Deterministic mock (tests / offline demo)
"""

from __future__ import annotations

import logging
import os

from .base import ChatChunk, LLMProvider, ToolCall

logger = logging.getLogger(__name__)


def get_provider(config: dict) -> LLMProvider:
    """Resolve and return the configured LLM provider.

    Raises RuntimeError if the requested provider is unavailable.
    """
    choice = config.get("llm_provider", "auto").lower()

    if choice == "mock":
        from .mock_provider import MockLLMProvider
        logger.info("LLM provider: Mock")
        return MockLLMProvider(config=config)

    if choice == "openrouter":
        provider = _make_openrouter(config)
        logger.info("LLM provider: OpenRouter (%s)", config.get("openrouter_model"))
        return provider

    if choice == "nvidia":
        provider = _make_nvidia(config)
        logger.info("LLM provider: NVIDIA NIM (%s)", config.get("nvidia_model"))
        return provider

    if choice == "google":
        provider = _make_google(config)
        logger.info("LLM provider: Google Gemini (%s)", config.get("google_model"))
        return provider

    if choice in ("groq", "auto"):
        provider = _try_groq(config)
        if provider is not None:
            logger.info("LLM provider: Groq (%s)", config.get("groq_model"))
            return provider
        if choice == "groq":
            raise RuntimeError("Groq requested but no API key found.")

    if choice in ("ollama", "auto"):
        from .ollama_provider import OllamaProvider
        provider = OllamaProvider(config)
        if provider.is_available():
            logger.info("LLM provider: Ollama (%s)", config.get("ollama_model"))
            return provider
        if choice == "ollama":
            raise RuntimeError("Ollama requested but unreachable.")

    raise RuntimeError(
        "No LLM provider available. "
        "Configure an API key in Settings → AI, or start Ollama locally."
    )


# ── Provider factories ────────────────────────────────────────────────────────

def _try_groq(config: dict) -> LLMProvider | None:
    api_key = config.get("groq_api_key") or ""
    if not api_key:
        env_var = config.get("groq_api_key_env", "GROQ_API_KEY")
        api_key = os.environ.get(env_var, "")
    if not api_key:
        return None
    try:
        from .groq_provider import GroqProvider
        return GroqProvider(config, api_key=api_key)
    except ImportError:
        logger.warning("Groq SDK not installed (`pip install groq`); falling back.")
        return None


def _make_openrouter(config: dict) -> LLMProvider:
    from .openai_compat_provider import OpenAICompatProvider
    api_key = config.get("openrouter_api_key") or ""
    if not api_key:
        raise RuntimeError("OpenRouter API key not configured. Add it in Settings → AI.")
    return OpenAICompatProvider(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        model=config.get("openrouter_model", "meta-llama/llama-3.3-70b-instruct"),
        timeout=float(config.get("openrouter_timeout_s", 60.0)),
        extra_headers={"HTTP-Referer": "https://github.com/kibo-app/kibo"},
    )


def _make_nvidia(config: dict) -> LLMProvider:
    from .openai_compat_provider import OpenAICompatProvider
    api_key = config.get("nvidia_api_key") or ""
    if not api_key:
        raise RuntimeError("NVIDIA API key not configured. Add it in Settings → AI.")
    return OpenAICompatProvider(
        api_key=api_key,
        base_url="https://integrate.api.nvidia.com/v1",
        model=config.get("nvidia_model", "meta/llama-3.3-70b-instruct"),
        timeout=float(config.get("nvidia_timeout_s", 60.0)),
    )


def _make_google(config: dict) -> LLMProvider:
    from .openai_compat_provider import OpenAICompatProvider
    api_key = config.get("google_api_key") or ""
    if not api_key:
        raise RuntimeError("Google API key not configured. Add it in Settings → AI.")
    return OpenAICompatProvider(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model=config.get("google_model", "gemini-2.0-flash"),
        timeout=float(config.get("google_timeout_s", 60.0)),
    )


__all__ = ["ChatChunk", "LLMProvider", "ToolCall", "get_provider"]
