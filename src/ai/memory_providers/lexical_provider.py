"""Lexical (keyword overlap + recency) memory provider.

The v4 retrieval strategy, preserved as a zero-dependency fallback when
sqlite-vec or fastembed are unavailable.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)


class LexicalProvider:
    """In-memory keyword scoring; no external dependencies."""

    def __init__(self) -> None:
        self._facts: dict[str, dict[str, Any]] = {}

    def is_available(self) -> bool:
        return True

    def store(
        self,
        *,
        fact_id: str,
        content: str,
        category: str,
        keywords: list[str],
        extracted_at: int,
    ) -> None:
        self._facts[fact_id] = {
            "id": fact_id,
            "content": content,
            "category": category,
            "keywords": keywords,
            "extracted_at": extracted_at,
        }

    def retrieve(self, query: str, max_results: int = 5) -> list[dict]:
        if not self._facts:
            return []

        tokens = set(
            query.lower()
            .replace(".", "")
            .replace("?", "")
            .replace(",", "")
            .split()
        )
        if not tokens:
            return []

        now = int(datetime.datetime.now().timestamp())
        scored: list[tuple[float, dict]] = []

        for f in self._facts.values():
            keywords = set(f.get("keywords", []))
            overlap = len(tokens & keywords)
            if overlap == 0:
                continue  # no keyword match — skip entirely

            score = overlap * 0.7
            days = max(0, (now - f.get("extracted_at", now)) / 86400)
            score += (1.0 / (1.0 + days)) * 0.2

            cat = f.get("category", "")
            if cat == "person":
                score += 0.015
            elif cat == "preference":
                score += 0.010

            scored.append((score, f))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:max_results]]

    def migrate(self, facts: list[dict]) -> None:
        for f in facts:
            fid = f.get("id")
            if fid and fid not in self._facts:
                self._facts[fid] = f
