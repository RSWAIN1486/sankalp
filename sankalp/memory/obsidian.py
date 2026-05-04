from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


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
            you.write_text(self._default_profile(), encoding="utf-8")
        else:
            text = you.read_text(encoding="utf-8")
            placeholder = "# You\n\nDurable facts about the user go here after promotion.\n"
            if text.strip() == placeholder.strip():
                you.write_text(self._default_profile(), encoding="utf-8")

    def profile_path(self) -> Path:
        return self.vault / "People" / "you.md"

    def read_profile(self) -> dict[str, Any]:
        path = self.profile_path()
        text = path.read_text(encoding="utf-8", errors="ignore")
        return {
            "path": str(path.relative_to(self.vault)),
            "self_profile": self._section(text, "User-authored profile"),
            "traits": self._traits(text),
            "raw": text,
        }

    def save_self_profile(self, value: str) -> None:
        path = self.profile_path()
        text = path.read_text(encoding="utf-8", errors="ignore")
        updated = self._replace_section(text, "User-authored profile", value.strip() + "\n")
        path.write_text(updated, encoding="utf-8")

    def add_inferred_trait(self, trait: str, evidence: str, confidence: str = "low") -> str | None:
        trait = trait.strip()
        if not trait:
            return None
        profile = self.read_profile()
        existing = {item["text"].lower() for item in profile["traits"]}
        if trait.lower() in existing:
            return None
        trait_id = uuid.uuid4().hex[:10]
        block = (
            f"\n<!-- sankalp:trait {trait_id} -->\n"
            f"### {trait[:72]}\n\n"
            f"ID: `{trait_id}`\n\n"
            f"Confidence: {confidence}\n\n"
            f"Evidence: {evidence.strip()[:240]}\n\n"
            f"{trait}\n"
            "<!-- /sankalp:trait -->\n"
        )
        path = self.profile_path()
        text = path.read_text(encoding="utf-8", errors="ignore")
        marker = "<!-- sankalp:traits:end -->"
        if marker in text:
            text = text.replace(marker, block + "\n" + marker)
        else:
            text += "\n## Agent-inferred traits\n\n<!-- sankalp:traits:start -->\n" + block + "\n<!-- sankalp:traits:end -->\n"
        path.write_text(text, encoding="utf-8")
        return trait_id

    def delete_trait(self, trait_id: str) -> bool:
        path = self.profile_path()
        text = path.read_text(encoding="utf-8", errors="ignore")
        pattern = rf"\n?<!-- sankalp:trait {re.escape(trait_id)} -->.*?<!-- /sankalp:trait -->\n?"
        updated, count = re.subn(pattern, "\n", text, flags=re.S)
        if count:
            path.write_text(updated, encoding="utf-8")
        return bool(count)

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

    def _default_profile(self) -> str:
        return (
            "# You\n\n"
            "## User-authored profile\n\n"
            "Add the way you want Sankalp to understand you here. This section is yours.\n\n"
            "## Agent-inferred traits\n\n"
            "<!-- sankalp:traits:start -->\n"
            "<!-- sankalp:traits:end -->\n"
        )

    def _section(self, text: str, heading: str) -> str:
        match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
        return match.group(1).strip() if match else ""

    def _replace_section(self, text: str, heading: str, value: str) -> str:
        pattern = rf"(^## {re.escape(heading)}\n)(.*?)(?=^## |\Z)"
        if re.search(pattern, text, flags=re.M | re.S):
            return re.sub(pattern, lambda match: match.group(1) + "\n" + value + "\n", text, count=1, flags=re.M | re.S)
        return text.rstrip() + f"\n\n## {heading}\n\n{value}\n"

    def _traits(self, text: str) -> list[dict[str, str]]:
        traits = []
        pattern = r"<!-- sankalp:trait ([a-f0-9]+) -->(.*?)<!-- /sankalp:trait -->"
        for match in re.finditer(pattern, text, flags=re.S):
            block = match.group(2).strip()
            title_match = re.search(r"^###\s+(.+)$", block, flags=re.M)
            confidence_match = re.search(r"^Confidence:\s*(.+)$", block, flags=re.M)
            evidence_match = re.search(r"^Evidence:\s*(.+)$", block, flags=re.M)
            text_parts = [part.strip() for part in block.split("\n\n") if part.strip()]
            traits.append({
                "id": match.group(1),
                "title": title_match.group(1).strip() if title_match else "Trait",
                "confidence": confidence_match.group(1).strip() if confidence_match else "low",
                "evidence": evidence_match.group(1).strip() if evidence_match else "",
                "text": text_parts[-1] if text_parts else "",
            })
        return traits
