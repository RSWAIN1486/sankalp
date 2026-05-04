from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Session:
    session_id: str
    title: str = "New session"
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    previous_response_id: str | None = None
    title_source: str = "new"

    def compact(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "title_source": self.title_source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.messages),
            "tool_call_count": len(self.tool_calls),
        }


class SessionStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def create(self) -> Session:
        session = Session(session_id=uuid.uuid4().hex[:12])
        self.save(session)
        return session

    def get(self, session_id: str | None) -> Session:
        if not session_id:
            return self.create()
        path = self._path(session_id)
        if not path.exists():
            return self.create()
        data = json.loads(path.read_text(encoding="utf-8"))
        return Session(**data)

    def save(self, session: Session) -> None:
        session.updated_at = time.time()
        self._path(session.session_id).write_text(json.dumps(asdict(session), indent=2), encoding="utf-8")

    def list(self) -> list[dict[str, Any]]:
        sessions = []
        for path in self.root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions.append(Session(**data).compact())
            except Exception:
                continue
        return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)

    def rename(self, session_id: str, title: str) -> Session:
        session = self.get(session_id)
        cleaned = " ".join(title.split()).strip()
        if cleaned:
            session.title = cleaned[:80]
            session.title_source = "manual"
            self.save(session)
        return session

    def update_generated_title(self, session_id: str, title: str) -> Session:
        session = self.get(session_id)
        cleaned = " ".join(title.split()).strip()
        if cleaned and session.title_source != "manual":
            session.title = cleaned[:64]
            session.title_source = "ai"
            self.save(session)
        return session

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True


def title_from_query(query: str) -> str:
    text = re.sub(r"\s+", " ", query).strip()
    text = re.sub(r"\b(attached|attachment):.*$", "", text, flags=re.I).strip()
    text = re.sub(r"^(can you|could you|please|pls|help me|i want to|i need to)\s+", "", text, flags=re.I)
    text = re.sub(r"^(check|find|look up|search for)\s+(for\s+)?(the\s+)?", "", text, flags=re.I)
    text = text.strip(" .?!")
    if not text:
        return "New session"
    words = text.split()
    title = " ".join(words[:5])
    return title[:64]
