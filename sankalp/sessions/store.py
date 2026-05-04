from __future__ import annotations

import json
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

    def compact(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
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
        if session.messages and session.title == "New session":
            first_user = next((m["content"] for m in session.messages if m.get("role") == "user"), "")
            session.title = first_user.strip().replace("\n", " ")[:64] or session.title
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
