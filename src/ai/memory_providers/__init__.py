"""Memory provider abstraction.

Auto-selects the best available backend:
  1. VectorProvider (sqlite-vec + fastembed bge-small-en) — semantic kNN
  2. LexicalProvider (keyword overlap + recency) — zero-dependency fallback
"""

from __future__ import annotations

import logging
from pathlib import Path

from .base import MemoryProvider
from .lexical_provider import LexicalProvider

logger = logging.getLogger(__name__)


def get_provider(config: dict, db_path: Path) -> MemoryProvider:
    """Return the best available memory provider.

    Args:
        config:  KIBO config dict (checked for memory_provider key).
        db_path: Path for the sqlite-vec database file.
    """
    choice = config.get("memory_provider", "auto").lower()

    if choice == "lexical":
        logger.info("Memory provider: lexical (forced by config)")
        return LexicalProvider()

    if choice in ("vector", "auto"):
        from .vector_provider import VectorProvider
        provider = VectorProvider(db_path)
        if provider.is_available():
            return provider
        if choice == "vector":
            raise RuntimeError(
                "Vector memory requested but sqlite-vec/fastembed unavailable. "
                "Install: pip install sqlite-vec fastembed"
            )

    logger.info("Memory provider: lexical (keyword overlap fallback)")
    return LexicalProvider()


__all__ = ["MemoryProvider", "get_provider"]
