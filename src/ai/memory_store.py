"""
memory_store.py — Obsidian-compatible memory vault for KIBO.

Memories are stored as Markdown files with YAML frontmatter in an Obsidian
vault at ~/.kibo/vault/memories/. Users can open this vault in Obsidian to
browse, search, and edit KIBO's memories visually.

An auto-generated index file (KIBO Dashboard.md) provides an overview
of all stored memories, grouped by category.
"""

import datetime
import logging
import re
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from PySide6.QtCore import QObject, Signal, Slot

from src.core.config_manager import get_user_data_dir
from src.ai.memory_providers import get_provider as _get_memory_provider

logger = logging.getLogger(__name__)

# ── YAML frontmatter helpers (no PyYAML dependency) ─────────────────────

_FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_LIST_ITEM = re.compile(r"^\s*-\s*(.+)$")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown text. Returns (meta, body)."""
    m = _FM_PATTERN.match(text)
    if not m:
        return {}, text

    meta: dict = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()

        # Parse inline list: [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            items = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
            meta[key] = items
        elif val.lower() in ("true", "false"):
            meta[key] = val.lower() == "true"
        elif val.isdigit():
            meta[key] = int(val)
        else:
            meta[key] = val.strip("'\"")

    body = text[m.end():]
    return meta, body.strip()


def _build_frontmatter(meta: dict) -> str:
    """Build YAML frontmatter string from a dict."""
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            items = ", ".join(str(i) for i in v)
            lines.append(f"{k}: [{items}]")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════

class MemoryStore(QObject):
    """Obsidian vault-based memory store with thread-safe caching."""

    facts_updated = Signal()

    def __init__(self, config: dict) -> None:
        super().__init__()
        self._config = config
        self._vault_dir = get_user_data_dir() / "vault"
        self._memory_dir = self._vault_dir / "memories"
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        self._dashboard_path = self._vault_dir / "KIBO Dashboard.md"

        self._lock = threading.Lock()
        self._cache: Dict[str, dict] = {}

        db_path = get_user_data_dir() / "memories.db"
        self._provider = _get_memory_provider(config, db_path)
        self._migration_done = threading.Event()

    # ── Public API ──────────────────────────────────────────────────────

    def extract_facts_async(self, conversation_text: str) -> None:
        """Extract memorable facts from conversation text in a background thread.

        Legacy path — kept as a fallback when the LLM provider can't emit
        inline `remember` tool calls. Skipped automatically if inline
        extraction is configured.
        """
        if not self._config.get("memory_enabled", True):
            return
        if self._config.get("memory_extraction_inline", True):
            return
        threading.Thread(target=self._extract_worker, args=(conversation_text,), daemon=True).start()

    @Slot(dict)
    def add_fact_inline(self, fact: dict) -> None:
        """Save a single fact emitted inline by the LLM as a `remember` tool call.

        Expects keys: content (str), category (str), keywords (list[str]).
        Thread-safe; can be invoked from any thread via QueuedConnection.
        """
        if not self._config.get("memory_enabled", True):
            return
        if not isinstance(fact, dict) or not fact.get("content"):
            return

        category = str(fact.get("category", "fact"))
        keywords = [str(k).lower() for k in fact.get("keywords", []) if k]
        content = str(fact["content"]).strip()

        now_ts = int(datetime.datetime.now().timestamp())
        with self._lock:
            self._enforce_cap_locked(extra=1)
            fact_id = self._write_fact_locked(content=content, category=category, keywords=keywords)
            self._cache.clear()

        self._provider.store(
            fact_id=fact_id,
            content=content,
            category=category,
            keywords=keywords,
            extracted_at=now_ts,
        )
        self._rebuild_dashboard()
        self.facts_updated.emit()

    def retrieve_relevant(self, query: str, max_results: int = 5) -> List[dict]:
        """Find memories relevant to the query via the configured provider."""
        if not self._migration_done.is_set():
            self._run_migration()

        return self._provider.retrieve(query, max_results)

    def build_memory_prompt(self, query: str) -> str:
        if not self._config.get("memory_enabled", True):
            return ""
        relevant = self.retrieve_relevant(query)
        if not relevant:
            return ""
        return "\n".join(f"- {f.get('content')}" for f in relevant)

    def clear_all_facts(self) -> None:
        """Delete all memory files and regenerate empty dashboard."""
        with self._lock:
            for p in self._memory_dir.glob("*.md"):
                try:
                    p.unlink()
                except Exception as e:
                    logger.error("Failed to delete memory %s: %s", p.name, e)
            self._cache.clear()
            self._provider.clear()
            self._migration_done.set()
        self._rebuild_dashboard()
        self.facts_updated.emit()

    # ── Loading ─────────────────────────────────────────────────────────

    def _load_all(self) -> List[dict]:
        """Load all memories from disk. Must be called with _lock held or from bg thread."""
        if self._cache:
            return list(self._cache.values())

        facts = []
        for p in self._memory_dir.glob("*.md"):
            try:
                text = p.read_text("utf-8")
                meta, body = _parse_frontmatter(text)
                if "id" in meta:
                    meta["content"] = body
                    facts.append(meta)
                    self._cache[meta["id"]] = meta
            except Exception:
                pass
        return facts

    # ── Background extraction worker ────────────────────────────────────

    def _extract_worker(self, conversation_text: str) -> None:
        model = self._config.get("memory_model", "qwen2.5-coder:7b")
        base_url = self._config.get("ollama_base_url", "http://localhost:11434")

        system_prompt = (
            'Extract 0-3 factual memories from this conversation. '
            'Return JSON array: [{"category": "preference | fact | person | location | task", '
            '"content": "...", "keywords": ["..."]}]. '
            'Only extract durable facts. Return [] if nothing worth remembering.'
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": conversation_text},
            ],
            "format": "json",
            "stream": False,
            "options": {"num_predict": 200},
        }

        try:
            import json
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(f"{base_url}/api/chat", json=payload)
                resp.raise_for_status()

            data = resp.json()
            content = data.get("message", {}).get("content", "[]")
            facts = json.loads(content)
            if not isinstance(facts, list):
                facts = []

            valid = [f for f in facts if isinstance(f, dict) and "content" in f and "keywords" in f]

            stored: list[tuple[str, str, str, list[str], int]] = []
            now_ts = int(datetime.datetime.now().timestamp())
            with self._lock:
                self._enforce_cap_locked(extra=len(valid))
                for f in valid:
                    content_s = str(f["content"]).strip()
                    cat_s = str(f.get("category", "fact"))
                    kw_s = [str(k).lower() for k in f["keywords"]]
                    fid = self._write_fact_locked(content=content_s, category=cat_s, keywords=kw_s)
                    stored.append((fid, content_s, cat_s, kw_s, now_ts))
                self._cache.clear()

            for fid, content_s, cat_s, kw_s, ts in stored:
                self._provider.store(
                    fact_id=fid, content=content_s, category=cat_s,
                    keywords=kw_s, extracted_at=ts,
                )

            if stored:
                self._rebuild_dashboard()
                self.facts_updated.emit()

        except Exception as e:
            logger.error("Memory extraction failed: %s", e)

    # ── Shared writers (must be called with _lock held) ─────────────────

    def _write_fact_locked(self, *, content: str, category: str, keywords: list[str]) -> str:
        """Write one fact to disk. Caller must hold _lock. Returns the fact_id."""
        now = datetime.datetime.now()
        fact_id = str(uuid.uuid4())[:8]
        slug = re.sub(r"[^a-z0-9]+", "-", content[:40].lower()).strip("-") or "memory"
        filename = f"{now.strftime('%Y-%m-%d')}_{category}_{slug}_{fact_id}.md"

        meta = {
            "id": fact_id,
            "category": category,
            "keywords": keywords,
            "extracted_at": int(now.timestamp()),
            "source_session": now.strftime("%Y-%m-%d"),
        }
        md_content = f"{_build_frontmatter(meta)}\n\n{content}\n"
        (self._memory_dir / filename).write_text(md_content, "utf-8")
        return fact_id

    def _enforce_cap_locked(self, *, extra: int) -> None:
        """Evict oldest facts to keep total <= memory_max_facts. Caller holds _lock."""
        existing = self._load_all()
        max_facts = self._config.get("memory_max_facts", 200)
        overflow = len(existing) + extra - max_facts
        if overflow <= 0:
            return
        to_evict = sorted(existing, key=lambda x: x.get("extracted_at", 0))[:overflow]
        evicted_ids: list[str] = []
        for old in to_evict:
            old_id = str(old.get("id", ""))
            if old_id:
                evicted_ids.append(old_id)
            for p in self._memory_dir.glob(f"*{old_id}*.md"):
                p.unlink(missing_ok=True)
        if evicted_ids:
            self._provider.delete(evicted_ids)
        self._cache.clear()

    # ── One-time migration ──────────────────────────────────────────────

    def _run_migration(self) -> None:
        """On first retrieve call, load Markdown memories into the provider.

        Double-checked locking via threading.Event prevents concurrent callers
        from both running migration. Runs synchronously so the first retrieve
        sees all persisted facts.
        """
        if self._migration_done.is_set():
            return
        with self._lock:
            if self._migration_done.is_set():
                return
            facts = self._load_all()
            if facts:
                # Normalise id to str — frontmatter parser converts digit-only
                # values to int, but providers require str keys.
                for f in facts:
                    if "id" in f:
                        f["id"] = str(f["id"])
                self._provider.migrate(facts)
            self._migration_done.set()

    # ── Dashboard generation ────────────────────────────────────────────

    def _rebuild_dashboard(self) -> None:
        """Generate an Obsidian-friendly dashboard linking all memories."""
        with self._lock:
            facts = self._load_all()

        grouped: Dict[str, List[dict]] = {}
        for f in facts:
            cat = f.get("category", "other")
            grouped.setdefault(cat, []).append(f)

        lines = [
            "# 🐾 KIBO Memory Dashboard",
            "",
            f"> Auto-generated. Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"> Total memories: {len(facts)}",
            "",
        ]

        category_icons = {
            "preference": "⭐", "fact": "📌", "person": "👤",
            "location": "📍", "task": "✅",
        }

        for cat in sorted(grouped.keys()):
            icon = category_icons.get(cat, "📝")
            lines.append(f"## {icon} {cat.title()}")
            lines.append("")
            for f in grouped[cat]:
                content = f.get("content", "")[:80]
                date = f.get("source_session", "unknown")
                lines.append(f"- {content} *({date})*")
            lines.append("")

        self._dashboard_path.write_text("\n".join(lines), "utf-8")
