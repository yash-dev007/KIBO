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
from PySide6.QtCore import QObject, Signal

from src.core.config_manager import get_user_data_dir

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

    # ── Public API ──────────────────────────────────────────────────────

    def extract_facts_async(self, conversation_text: str) -> None:
        """Extract memorable facts from conversation text in a background thread."""
        if not self._config.get("memory_enabled", True):
            return
        threading.Thread(target=self._extract_worker, args=(conversation_text,), daemon=True).start()

    def retrieve_relevant(self, query: str, max_results: int = 5) -> List[dict]:
        """Find memories relevant to the query using keyword overlap + recency."""
        with self._lock:
            facts = self._load_all()

        if not facts:
            return []

        tokens = set(query.lower().replace(".", "").replace("?", "").replace(",", "").split())
        if not tokens:
            return []

        now = int(datetime.datetime.now().timestamp())
        scored = []

        for f in facts:
            keywords = set(f.get("keywords", []))
            overlap = len(tokens & keywords)
            score = overlap * 0.7

            extracted_at = f.get("extracted_at", now)
            days = max(0, (now - extracted_at) / 86400)
            score += (1.0 / (1.0 + days)) * 0.2

            cat = f.get("category", "")
            if cat == "person":
                score += 0.015
            elif cat == "preference":
                score += 0.010

            if score > 0:
                scored.append((score, f))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:max_results]]

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

            # Enforce max facts cap
            with self._lock:
                existing = self._load_all()
                max_facts = self._config.get("memory_max_facts", 200)
                total = len(existing) + len(valid)
                if total > max_facts:
                    to_evict = sorted(existing, key=lambda x: x.get("extracted_at", 0))
                    for old in to_evict[: total - max_facts]:
                        old_id = old.get("id", "")
                        for p in self._memory_dir.glob(f"*{old_id}*.md"):
                            p.unlink(missing_ok=True)
                    self._cache.clear()

            now = datetime.datetime.now()
            new_count = 0

            for f in valid:
                fact_id = str(uuid.uuid4())[:8]
                category = f.get("category", "fact")
                keywords = [str(k).lower() for k in f["keywords"]]

                # Build sanitized filename
                slug = re.sub(r"[^a-z0-9]+", "-", f["content"][:40].lower()).strip("-")
                filename = f"{now.strftime('%Y-%m-%d')}_{category}_{slug}.md"

                meta = {
                    "id": fact_id,
                    "category": category,
                    "keywords": keywords,
                    "extracted_at": int(now.timestamp()),
                    "source_session": now.strftime("%Y-%m-%d"),
                }

                md_content = f"{_build_frontmatter(meta)}\n\n{f['content']}\n"

                path = self._memory_dir / filename
                path.write_text(md_content, "utf-8")
                new_count += 1

            if new_count > 0:
                with self._lock:
                    self._cache.clear()
                self._rebuild_dashboard()
                self.facts_updated.emit()

        except Exception as e:
            logger.error("Memory extraction failed: %s", e)

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
