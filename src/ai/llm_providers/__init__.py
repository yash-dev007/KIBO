"""LLM provider abstraction.

Selects the best available backend (Groq cloud free tier > Ollama local)
based on config + environment.
"""

from __future__ import annotations

import logging
import os

from .base import ChatChunk, LLMProvider, ToolCall

logger = logging.getLogger(__name__)


def get_provider(config: dict) -> LLMProvider:
    """Resolve which LLM provider to use based on config + env.

    Order of preference when llm_provider == "auto":
      1. Groq (if API key present and SDK installed)
      2. Ollama (if reachable)

    Returns the chosen provider; raises RuntimeError if none usable.
    """
    choice = config.get("llm_provider", "auto").lower()

    if choice in ("groq", "auto"):
        provider = _try_groq(config)
        if provider is not None:
            logger.info("LLM provider: Groq (%s)", config.get("groq_model"))
            return provider
        if choice == "groq":
            raise RuntimeError("Groq requested but unavailable (missing API key or SDK).")

    if choice in ("ollama", "auto"):
        from .ollama_provider import OllamaProvider
        provider = OllamaProvider(config)
        if provider.is_available():
            logger.info("LLM provider: Ollama (%s)", config.get("ollama_model"))
            return provider
        if choice == "ollama":
            raise RuntimeError("Ollama requested but unreachable.")

    raise RuntimeError("No LLM provider available. Set GROQ_API_KEY or start Ollama.")


def _try_groq(config: dict):
    env_var = config.get("groq_api_key_env", "GROQ_API_KEY")
    if not os.environ.get(env_var):
        return None
    try:
        from .groq_provider import GroqProvider
        return GroqProvider(config)
    except ImportError:
        logger.warning("Groq SDK not installed (`pip install groq`); falling back.")
        return None


__all__ = ["ChatChunk", "LLMProvider", "ToolCall", "get_provider"]
