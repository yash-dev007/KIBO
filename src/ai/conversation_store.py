"""
conversation_store.py — JSON-file-backed conversation persistence.

Storage: ~/.kibo/conversations/{id}.json  (one file per conversation)
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _is_valid_id(conv_id: object) -> bool:
    """Reject any conv_id that isn't a canonical UUID v4 string.

    Prevents path traversal (e.g. '../etc/passwd') from reaching the filesystem.
    """
    return isinstance(conv_id, str) and bool(_UUID_RE.match(conv_id))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Message:
    id: str
    role: str
    text: str
    timestamp: str


@dataclass
class Conversation:
    id: str
    title: str
    messages: list[Message]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "messages": [asdict(m) for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        return cls(
            id=data["id"],
            title=data.get("title", "New conversation"),
            messages=[Message(**m) for m in data.get("messages", [])],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def meta(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.messages),
        }


class ConversationStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "conversations"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create(self) -> Conversation:
        conv = Conversation(
            id=str(uuid.uuid4()),
            title="New conversation",
            messages=[],
            created_at=_now(),
            updated_at=_now(),
        )
        self._write(conv)
        return conv

    def get(self, conv_id: str) -> Optional[Conversation]:
        if not _is_valid_id(conv_id):
            return None
        path = self._dir / f"{conv_id}.json"
        if not path.exists():
            return None
        try:
            return Conversation.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.error("Failed to load conversation %s: %s", conv_id, exc)
            return None

    def list_all(self) -> list:
        result = []
        for path in self._dir.glob("*.json"):
            if not _is_valid_id(path.stem):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                result.append({
                    "id": data["id"],
                    "title": data.get("title", "New conversation"),
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"],
                    "message_count": len(data.get("messages", [])),
                })
            except Exception as exc:
                logger.warning("Skipping malformed conversation file %s: %s", path.name, exc)
                continue
        return sorted(result, key=lambda c: c["updated_at"], reverse=True)

    def delete(self, conv_id: str) -> bool:
        if not _is_valid_id(conv_id):
            return False
        path = self._dir / f"{conv_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def add_message(self, conv_id: str, role: str, text: str) -> Optional[Message]:
        if not _is_valid_id(conv_id):
            return None
        if not text.strip():
            return None
        with self._lock:
            conv = self.get(conv_id)
            if conv is None:
                return None
            msg = Message(id=str(uuid.uuid4()), role=role, text=text.strip(), timestamp=_now())
            conv.messages.append(msg)
            conv.updated_at = _now()
            if len(conv.messages) == 1 and role == "user":
                title = text.strip()
                conv.title = title[:60] + ("…" if len(title) > 60 else "")
            self._write(conv)
            return msg

    def _write(self, conv: Conversation) -> None:
        path = self._dir / f"{conv.id}.json"
        path.write_text(json.dumps(conv.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
