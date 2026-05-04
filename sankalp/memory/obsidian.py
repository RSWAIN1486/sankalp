from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class MemoryHit:
    path: str
    title: str
    snippet: str
    score: int


class ObsidianMemory:
    def __init__(self, vault: Path):
        self.vault = vault
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.vault.mkdir(parents=True, exist_ok=True)
        for name in ["People", "Projects", "Sessions", "Skills", "Inbox", "Decisions"]:
            (self.vault / name).mkdir(parents=True, exist_ok=True)
        you = self.vault / "People" / "you.md"
        if not you.exists():
            you.write_text("# You\n\nDurable facts about the user go here after promotion.\n", encoding="utf-8")

    def capture(self, text: str, source: str = "chat") -> Path:
        now = datetime.now()
        path = self.vault / "Inbox" / f"{now:%Y-%m-%d}.md"
        entry = f"\n## {now:%H:%M:%S} - {source}\n\n{text.strip()}\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return path

    def append_session_turn(self, session_id: str, role: str, content: str) -> Path:
        now = datetime.now()
        path = self.vault / "Sessions" / f"{now:%Y-%m-%d}-{session_id}.md"
        if not path.exists():
            path.write_text(f"# Session {session_id}\n\nCreated: {now.isoformat(timespec='seconds')}\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n## {role.title()} - {now:%H:%M:%S}\n\n{content.strip()}\n")
        return path

    def list_recent(self, limit: int = 20) -> list[dict[str, str]]:
        notes = [p for p in self.vault.rglob("*.md") if p.is_file()]
        notes.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        result = []
        for path in notes[:limit]:
            result.append({
                "path": str(path.relative_to(self.vault)),
                "title": path.stem,
                "preview": path.read_text(encoding="utf-8", errors="ignore")[:500],
            })
        return result

    def retrieve(self, query: str, limit: int = 6) -> list[MemoryHit]:
        terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9_]{3,}", query)}
        if not terms:
            return []
        hits: list[MemoryHit] = []
        for path in self.vault.rglob("*.md"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            lower = text.lower()
            score = sum(lower.count(term) for term in terms)
            if score <= 0:
                continue
            snippet = self._best_snippet(text, terms)
            hits.append(MemoryHit(str(path.relative_to(self.vault)), path.stem, snippet, score))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]

    def _best_snippet(self, text: str, terms: set[str]) -> str:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not paragraphs:
            return ""
        best = max(paragraphs, key=lambda part: sum(part.lower().count(term) for term in terms))
        return best[:700]
