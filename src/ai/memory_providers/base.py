"""Protocol for memory retrieval backends."""

from __future__ import annotations

from typing import Protocol


class MemoryProvider(Protocol):
    """Interface every memory backend must implement."""

    def is_available(self) -> bool: ...

    def store(
        self,
        *,
        fact_id: str,
        content: str,
        category: str,
        keywords: list[str],
        extracted_at: int,
    ) -> None:
        """Persist a single fact. Called from within MemoryStore's lock."""
        ...

    def retrieve(self, query: str, max_results: int = 5) -> list[dict]:
        """Return up to max_results facts relevant to query.

        Each dict must have at least: id, content, category, keywords, extracted_at.
        """
        ...

    def migrate(self, facts: list[dict]) -> None:
        """Ingest facts loaded from Markdown files (idempotent — skip existing ids)."""
        ...

    def delete(self, fact_ids: list[str]) -> None:
        """Remove facts by id from the provider index."""
        ...

    def clear(self) -> None:
        """Remove all indexed facts."""
        ...
