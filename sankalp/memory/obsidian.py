from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote


@dataclass
class MemoryHit:
    path: str
    title: str
    snippet: str
    score: int
    text: str


class ObsidianMemory:
    def __init__(self, vault: Path, workspace: str = ""):
        self.vault = vault
        self.workspace = workspace.strip().strip("/")
        self.access_error: str | None = None
        self.ensure_schema()

    def ensure_schema(self) -> None:
        try:
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
        except Exception as exc:
            self.access_error = str(exc)

    def profile_path(self) -> Path:
        return self.vault / "People" / "you.md"

    def read_profile(self) -> dict[str, Any]:
        path = self.profile_path()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            return {
                "path": str(path),
                "self_profile": "",
                "traits": [],
                "raw": "",
                "error": str(exc),
            }
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
        root = self.content_root()
        try:
            notes = [p for p in root.rglob("*.md") if p.is_file()]
        except Exception as exc:
            return [{"path": str(root), "title": "Memory access error", "preview": str(exc)}]
        notes.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        result = []
        for path in notes[:limit]:
            result.append({
                "path": self._display_path(path),
                "title": path.stem,
                "preview": path.read_text(encoding="utf-8", errors="ignore")[:500],
            })
        return result

    def retrieve(self, query: str, limit: int = 6) -> list[MemoryHit]:
        terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9_]{3,}", query)}
        if not terms:
            return []
        hits: list[MemoryHit] = []
        try:
            paths = list(self.vault.rglob("*.md"))
        except Exception:
            return []
        for path in paths:
            if not path.is_file() or self._is_ignored_retrieval_path(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            display_path = self._display_path(path)
            lower = text.lower()
            path_text = f"{display_path} {path.stem}".lower()
            score = sum(lower.count(term) for term in terms)
            score += 3 * sum(path_text.count(term) for term in terms)
            if score <= 0:
                continue
            snippet = self._best_snippet(text, terms)
            hits.append(MemoryHit(display_path, path.stem, snippet, score, self._note_text_for_context(text)))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]

    def content_root(self) -> Path:
        if not self.workspace:
            return self.vault
        candidate = (self.vault / self.workspace).resolve()
        try:
            candidate.relative_to(self.vault.resolve())
        except ValueError:
            return self.vault
        return candidate

    def status(self) -> dict[str, Any]:
        root = self.content_root()
        return {
            "vault": str(self.vault),
            "workspace": self.workspace,
            "root": str(root),
            "accessible": self.access_error is None and self._can_list(root),
            "error": self.access_error or self._list_error(root),
        }

    def tree(self, max_depth: int = 4) -> dict[str, Any]:
        root = self.content_root()
        error = self._list_error(root)
        if error:
            return {"root": str(root), "items": [], "error": error}
        return {"root": str(root), "items": self._tree_items(root, root, 0, max_depth), "error": None}

    def folders(self) -> list[dict[str, str]]:
        root = self.vault
        error = self._list_error(root)
        if error:
            return []
        folders = [{"path": "", "name": "Whole vault"}]
        try:
            children = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except Exception:
            return folders
        for path in (p for p in children if p.is_dir() and not self._has_hidden_part(p)):
            try:
                rel = str(path.resolve().relative_to(root.resolve()))
            except ValueError:
                continue
            folders.append({"path": rel, "name": path.name})
        return folders

    def children(self, folder: str | None = None) -> dict[str, Any]:
        root = self._safe_folder(folder or self.workspace)
        error = self._list_error(root)
        if error:
            return {"folder": self._display_path(root), "items": [], "error": error}
        items = []
        try:
            children = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception as exc:
            return {"folder": self._display_path(root), "items": [], "error": str(exc)}
        for child in children:
            if child.name.startswith("."):
                continue
            if child.is_dir():
                items.append({"type": "directory", "name": child.name, "path": self._display_path(child)})
            elif child.suffix.lower() == ".md":
                items.append({
                    "type": "file",
                    "name": child.name,
                    "path": self._display_path(child),
                    "obsidian_uri": self.obsidian_uri(self._display_path(child)),
                })
        return {"folder": self._display_path(root), "items": items, "error": None}

    def notes(self, folder: str | None = None, limit: int = 200) -> dict[str, Any]:
        root = self._safe_folder(folder or self.workspace)
        error = self._list_error(root)
        if error:
            return {"folder": self._display_path(root), "notes": [], "error": error}
        notes = []
        try:
            paths = sorted(root.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception as exc:
            return {"folder": self._display_path(root), "notes": [], "error": str(exc)}
        for path in paths[:limit]:
            notes.append({
                "name": path.name,
                "path": self._display_path(path),
                "preview": path.read_text(encoding="utf-8", errors="ignore")[:700],
                "obsidian_uri": self.obsidian_uri(self._display_path(path)),
            })
        return {"folder": self._display_path(root), "notes": notes, "error": None}

    def open_target(self, target: str) -> dict[str, Any]:
        path = self._safe_folder_or_file(target)
        if not path.exists():
            return {"ok": False, "error": "path does not exist", "path": str(path)}
        if path.is_file() and path.suffix.lower() == ".md":
            uri = self.obsidian_uri(self._display_path(path))
            return {"ok": True, "mode": "obsidian", "uri": uri}
        return {"ok": True, "mode": "finder", "path": str(path)}

    def obsidian_uri(self, note_path: str) -> str:
        vault_name = self.vault.name
        clean = note_path[:-3] if note_path.endswith(".md") else note_path
        return f"obsidian://open?vault={quote(vault_name)}&file={quote(clean)}"

    def _best_snippet(self, text: str, terms: set[str]) -> str:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not paragraphs:
            return ""
        best = max(paragraphs, key=lambda part: sum(part.lower().count(term) for term in terms))
        return best[:700]

    def _note_text_for_context(self, text: str, limit: int = 4000) -> str:
        return text.strip()[:limit]

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.vault.resolve()))
        except ValueError:
            return str(path)

    def _is_ignored_retrieval_path(self, path: Path) -> bool:
        try:
            rel = path.resolve().relative_to(self.vault.resolve())
        except ValueError:
            return True
        if any(part.startswith(".") for part in rel.parts):
            return True
        return bool(rel.parts and rel.parts[0].lower() == "sessions")

    def _tree_items(self, root: Path, path: Path, depth: int, max_depth: int) -> list[dict[str, Any]]:
        if depth >= max_depth:
            return []
        items = []
        try:
            children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            return []
        for child in children:
            if child.name.startswith("."):
                continue
            if child.is_dir():
                items.append({
                    "type": "directory",
                    "name": child.name,
                    "path": str(child.relative_to(root)),
                    "children": self._tree_items(root, child, depth + 1, max_depth),
                })
            elif child.suffix.lower() == ".md":
                items.append({
                    "type": "file",
                    "name": child.name,
                    "path": str(child.relative_to(root)),
                })
        return items

    def _safe_folder(self, folder: str) -> Path:
        if not folder:
            return self.vault
        candidate = (self.vault / folder.strip().strip("/")).resolve()
        try:
            candidate.relative_to(self.vault.resolve())
            if candidate.is_dir():
                return candidate
        except ValueError:
            pass
        return self.vault

    def _safe_folder_or_file(self, target: str) -> Path:
        candidate = (self.vault / target.strip().strip("/")).resolve()
        try:
            candidate.relative_to(self.vault.resolve())
            return candidate
        except ValueError:
            return self.vault

    def _has_hidden_part(self, path: Path) -> bool:
        try:
            rel = path.resolve().relative_to(self.vault.resolve())
        except ValueError:
            return True
        return any(part.startswith(".") for part in rel.parts)

    def _can_list(self, path: Path) -> bool:
        return self._list_error(path) is None

    def _list_error(self, path: Path) -> str | None:
        try:
            next(path.iterdir(), None)
            return None
        except StopIteration:
            return None
        except Exception as exc:
            return str(exc)

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
