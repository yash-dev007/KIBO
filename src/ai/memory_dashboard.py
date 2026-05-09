"""memory_dashboard.py — Obsidian dashboard generator for KIBO memories."""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Dict, List

_CATEGORY_ICONS: Dict[str, str] = {
    "preference": "⭐", "fact": "📌", "person": "👤",
    "location": "📍", "task": "✅",
}


class MemoryDashboard:
    """Writes an Obsidian-friendly index of all memory facts to a Markdown file."""

    def rebuild(self, facts: List[dict], output_path: Path) -> None:
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

        for cat in sorted(grouped.keys()):
            icon = _CATEGORY_ICONS.get(cat, "📝")
            lines.append(f"## {icon} {cat.title()}")
            lines.append("")
            for f in grouped[cat]:
                content = f.get("content", "")[:80]
                date = f.get("source_session", "unknown")
                lines.append(f"- {content} *({date})*")
            lines.append("")

        output_path.write_text("\n".join(lines), "utf-8")
