"""Vector memory provider using sqlite-vec + fastembed.

Stores embeddings in a local SQLite database alongside the memory records.
Retrieval uses kNN search over 384-dim bge-small-en vectors.

Falls back gracefully if either dependency is missing.
"""

from __future__ import annotations

import logging
import sqlite3
import struct
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EMBED_DIM = 384
_MODEL_NAME = "BAAI/bge-small-en-v1.5"


def _serialize(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


class VectorProvider:
    """sqlite-vec backed semantic search with fastembed bge-small embeddings."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._embedder: Any = None
        self._ready = False
        self._db_lock = threading.Lock()
        self._setup()

    def _setup(self) -> None:
        try:
            import sqlite_vec
            from fastembed import TextEmbedding

            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)

            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id          TEXT PRIMARY KEY,
                    content     TEXT NOT NULL,
                    category    TEXT NOT NULL DEFAULT 'fact',
                    keywords    TEXT NOT NULL DEFAULT '[]',
                    extracted_at INTEGER NOT NULL DEFAULT 0
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(
                    id          TEXT PRIMARY KEY,
                    embedding   float[384]
                );
            """)
            self._conn.commit()

            self._embedder = TextEmbedding(model_name=_MODEL_NAME)
            self._ready = True
            logger.info("VectorProvider ready (sqlite-vec + fastembed bge-small-en)")
        except ImportError as exc:
            logger.warning("VectorProvider unavailable (missing deps): %s — falling back to lexical", exc)
            self._ready = False
        except Exception as exc:
            logger.error("VectorProvider setup failed: %s", exc, exc_info=True)
            self._ready = False

    def is_available(self) -> bool:
        return self._ready

    def store(
        self,
        *,
        fact_id: str,
        content: str,
        category: str,
        keywords: list[str],
        extracted_at: int,
    ) -> None:
        if not self._ready or self._conn is None:
            return

        import json
        vec = next(self._embedder.embed([content]))
        blob = _serialize(vec.tolist())

        with self._db_lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO memories (id, content, category, keywords, extracted_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (fact_id, content, category, json.dumps(keywords), extracted_at),
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO memories_vec (id, embedding) VALUES (?, ?)",
                (fact_id, blob),
            )
            self._conn.commit()

    def retrieve(self, query: str, max_results: int = 5) -> list[dict]:
        if not self._ready or self._conn is None:
            return []

        import json
        q_vec = next(self._embedder.embed([query]))
        blob = _serialize(q_vec.tolist())

        with self._db_lock:
            rows = self._conn.execute(
                """
                SELECT m.id, m.content, m.category, m.keywords, m.extracted_at
                FROM memories_vec AS mv
                JOIN memories AS m ON m.id = mv.id
                WHERE mv.embedding MATCH ?
                  AND k = ?
                ORDER BY distance
                """,
                (blob, max_results),
            ).fetchall()

        return [
            {
                "id": r[0],
                "content": r[1],
                "category": r[2],
                "keywords": json.loads(r[3]),
                "extracted_at": r[4],
            }
            for r in rows
        ]

    def migrate(self, facts: list[dict]) -> None:
        """Embed and store any facts not yet in the vector DB."""
        if not self._ready or self._conn is None:
            return

        with self._db_lock:
            existing_ids: set[str] = {
                row[0]
                for row in self._conn.execute("SELECT id FROM memories").fetchall()
            }

        to_add = [f for f in facts if f.get("id") and f["id"] not in existing_ids]
        if not to_add:
            return

        logger.info("VectorProvider: migrating %d legacy memories", len(to_add))
        import json
        contents = [f.get("content", "") for f in to_add]
        embeddings = list(self._embedder.embed(contents))

        with self._db_lock:
            for fact, vec in zip(to_add, embeddings):
                blob = _serialize(vec.tolist())
                fid = fact["id"]
                keywords = fact.get("keywords", [])
                self._conn.execute(
                    "INSERT OR IGNORE INTO memories (id, content, category, keywords, extracted_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        fid,
                        fact.get("content", ""),
                        fact.get("category", "fact"),
                        json.dumps(keywords),
                        fact.get("extracted_at", 0),
                    ),
                )
                self._conn.execute(
                    "INSERT OR IGNORE INTO memories_vec (id, embedding) VALUES (?, ?)",
                    (fid, blob),
                )
            self._conn.commit()
        logger.info("VectorProvider: migration complete")
