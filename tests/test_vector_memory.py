"""tests/test_vector_memory.py — Tests for memory provider abstraction.

Covers both the LexicalProvider (always available) and VectorProvider
(only if sqlite-vec + fastembed are installed).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── LexicalProvider ──────────────────────────────────────────────────────────

class TestLexicalProvider:
    def _make(self):
        from src.ai.memory_providers.lexical_provider import LexicalProvider
        return LexicalProvider()

    def test_is_available(self):
        p = self._make()
        assert p.is_available()

    def test_store_and_retrieve_keyword_match(self):
        p = self._make()
        p.store(
            fact_id="abc1",
            content="User drinks espresso every morning",
            category="preference",
            keywords=["espresso", "coffee", "morning", "drinks"],
            extracted_at=int(time.time()),
        )
        results = p.retrieve("favorite coffee drink", max_results=3)
        assert len(results) == 1
        assert "espresso" in results[0]["content"]

    def test_no_match_returns_empty(self):
        p = self._make()
        p.store(
            fact_id="abc2",
            content="User lives in Berlin",
            category="location",
            keywords=["berlin", "lives", "city"],
            extracted_at=int(time.time()),
        )
        results = p.retrieve("favorite food", max_results=5)
        assert results == []

    def test_migrate_skips_existing_ids(self):
        p = self._make()
        fact = {
            "id": "migr1",
            "content": "User prefers dark mode",
            "category": "preference",
            "keywords": ["dark", "mode"],
            "extracted_at": int(time.time()),
        }
        p.migrate([fact, fact])  # duplicate — should not double-insert
        p.migrate([fact])        # again
        results = p.retrieve("dark mode", max_results=5)
        assert len(results) == 1

    def test_recency_scores_newer_higher(self):
        p = self._make()
        old_ts = int(time.time()) - 86400 * 30  # 30 days ago
        new_ts = int(time.time())
        p.store(
            fact_id="old1",
            content="User likes jazz music",
            category="preference",
            keywords=["jazz", "music", "likes"],
            extracted_at=old_ts,
        )
        p.store(
            fact_id="new1",
            content="User likes jazz music",
            category="preference",
            keywords=["jazz", "music", "likes"],
            extracted_at=new_ts,
        )
        results = p.retrieve("jazz music", max_results=5)
        assert results[0]["id"] == "new1"


# ── VectorProvider ────────────────────────────────────────────────────────────

def _vector_available() -> bool:
    try:
        import sqlite_vec  # noqa: F401
        from fastembed import TextEmbedding  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _vector_available(), reason="sqlite-vec or fastembed not installed")
class TestVectorProvider:
    @pytest.fixture
    def provider(self, tmp_path):
        from src.ai.memory_providers.vector_provider import VectorProvider
        p = VectorProvider(tmp_path / "test_mem.db")
        assert p.is_available(), "VectorProvider failed to initialise"
        return p

    def test_store_and_retrieve_semantic(self, provider):
        provider.store(
            fact_id="v001",
            content="The user enjoys drinking espresso each morning",
            category="preference",
            keywords=["espresso", "coffee"],
            extracted_at=int(time.time()),
        )
        results = provider.retrieve("What does the user drink?", max_results=3)
        assert len(results) >= 1
        assert results[0]["id"] == "v001"

    def test_migrate_idempotent(self, provider):
        fact = {
            "id": "m001",
            "content": "User's name is Alex",
            "category": "person",
            "keywords": ["name", "alex"],
            "extracted_at": int(time.time()),
        }
        provider.migrate([fact])
        provider.migrate([fact])  # second call must not error or duplicate
        results = provider.retrieve("user name", max_results=5)
        assert sum(1 for r in results if r["id"] == "m001") == 1

    def test_retrieve_returns_dicts_with_required_keys(self, provider):
        provider.store(
            fact_id="v002",
            content="User works as a software engineer",
            category="fact",
            keywords=["software", "engineer", "job"],
            extracted_at=int(time.time()),
        )
        results = provider.retrieve("job profession", max_results=1)
        assert results
        required = {"id", "content", "category", "keywords", "extracted_at"}
        assert required.issubset(results[0].keys())


# ── Factory (get_provider) ────────────────────────────────────────────────────

class TestGetProvider:
    def test_auto_returns_provider(self, tmp_path):
        from src.ai.memory_providers import get_provider
        p = get_provider({}, tmp_path / "mem.db")
        assert p.is_available()

    def test_lexical_forced(self, tmp_path):
        from src.ai.memory_providers import get_provider
        from src.ai.memory_providers.lexical_provider import LexicalProvider
        p = get_provider({"memory_provider": "lexical"}, tmp_path / "mem.db")
        assert isinstance(p, LexicalProvider)
