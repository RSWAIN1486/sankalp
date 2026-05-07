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

    def capture(self, text: str, source: str = "chat", folder: str | None = None, note: str | None = None) -> Path:
        return self.capture_smart(text, source=source, folder=folder, note=note)

    def capture_smart(self, text: str, source: str = "chat", folder: str | None = None, note: str | None = None) -> Path:
        plan = self._remember_plan(text, folder=folder, note=note)
        folder = self._safe_folder_path(plan["folder"])
        note_name = self._safe_note_name(plan["note"])
        path = folder / note_name
        now = datetime.now()
        entry = f"\n## {now:%H:%M:%S} - {source}\n\n{text.strip()}\n"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            title = path.stem.replace("-", " ").strip().title()
            path.write_text(f"# {title}\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return path

    def remember_target(self, text: str, folder: str | None = None, note: str | None = None) -> dict[str, str]:
        plan = self._remember_plan(text, folder=folder, note=note)
        folder = self._safe_folder_path(plan["folder"])
        note_name = self._safe_note_name(plan["note"])
        path = folder / note_name
        return {"folder": self._display_path(folder), "note": note_name, "path": self._display_path(path)}

    def folder_paths(self, max_depth: int = 5) -> list[str]:
        root = self.vault
        if self._list_error(root):
            return []
        paths: list[str] = []
        try:
            for path in root.rglob("*"):
                if not path.is_dir():
                    continue
                if self._has_hidden_part(path):
                    continue
                rel = self._display_path(path)
                if not rel or rel == ".":
                    continue
                depth = len(Path(rel).parts)
                if depth > max_depth:
                    continue
                if rel.split("/")[0].lower() == "sessions":
                    continue
                paths.append(rel)
        except Exception:
            return []
        return sorted(set(paths), key=str.lower)

    def append_session_turn(self, session_id: str, role: str, content: str) -> Path:
        now = datetime.now()
        path = self.vault / "Sessions" / f"{now:%Y-%m-%d}-{session_id}.md"
        if not path.exists():
            path.write_text(f"# Session {session_id}\n\nCreated: {now.isoformat(timespec='seconds')}\n", encoding="utf-8")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n## {role.title()} - {now:%H:%M:%S}\n\n{content.strip()}\n")
        return path

    def delete_session_notes(self, session_id: str) -> int:
        if not re.fullmatch(r"[a-f0-9]{12}", session_id):
            return 0
        root = self.vault / "Sessions"
        try:
            paths = list(root.glob(f"*-{session_id}.md"))
        except Exception:
            return 0
        deleted = 0
        for path in paths:
            try:
                path.unlink()
                deleted += 1
            except Exception:
                continue
        return deleted

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
        terms = self._query_terms(query)
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
        return self._focused_hits(hits, limit)

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

    def _query_terms(self, query: str) -> set[str]:
        stopwords = {
            "about", "around", "check", "from", "memory", "notes", "note", "documentation",
            "document", "used", "using", "what", "which", "where", "when", "why", "how",
            "does", "did", "the", "for", "can", "you", "any", "was", "were", "there",
        }
        return {
            term.lower()
            for term in re.findall(r"[a-zA-Z0-9_]{3,}", query)
            if term.lower() not in stopwords
        }

    def _focused_hits(self, hits: list[MemoryHit], limit: int) -> list[MemoryHit]:
        if not hits:
            return []
        top_score = hits[0].score
        threshold = max(2, int(top_score * 0.35))
        focused = [hit for hit in hits if hit.score >= threshold]
        return focused[:limit]

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

    def _safe_folder_path(self, folder: str) -> Path:
        if not folder:
            return self.vault
        candidate = (self.vault / folder.strip().strip("/")).resolve()
        try:
            candidate.relative_to(self.vault.resolve())
            return candidate
        except ValueError:
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

    def _remember_plan(self, text: str, folder: str | None = None, note: str | None = None) -> dict[str, str]:
        if folder or note:
            return {"folder": folder or "Inbox", "note": note or self._infer_note_name(text)}
        explicit = self._parse_explicit_remember_target(text)
        if explicit:
            folder = explicit.get("folder") or "Inbox"
            note = explicit.get("note") or f"{datetime.now():%Y-%m-%d}.md"
            return {"folder": folder, "note": note}

        best = self._best_existing_note(text)
        if best is not None and best.score >= 3:
            note_path = Path(best.path)
            folder = str(note_path.parent).strip(".")
            return {"folder": folder or "Inbox", "note": note_path.name}

        folder = self._best_folder_for_text(text)
        note = self._infer_note_name(text)
        return {"folder": folder, "note": note}

    def _parse_explicit_remember_target(self, text: str) -> dict[str, str] | None:
        content = text.strip()
        marker = re.search(r"(?:^|\n)\s*(?:folder|path)\s*:\s*(.+)\s*$", content, flags=re.I | re.M)
        note_marker = re.search(r"(?:^|\n)\s*(?:note|file|title)\s*:\s*(.+)\s*$", content, flags=re.I | re.M)
        folder = marker.group(1).strip() if marker else ""
        note = note_marker.group(1).strip() if note_marker else ""
        if folder or note:
            return {"folder": folder, "note": note}

        inline = re.search(r"(?:save|remember|document)\s+(?:this\s+)?(?:to|in)\s+([A-Za-z0-9 _\-/]+/[^:\n]+)", content, flags=re.I)
        if inline:
            raw = inline.group(1).strip().strip(".")
            candidate = Path(raw)
            if candidate.suffix.lower() == ".md":
                return {"folder": str(candidate.parent), "note": candidate.name}
            return {"folder": raw, "note": ""}
        return None

    def _best_existing_note(self, text: str) -> MemoryHit | None:
        terms = self._query_terms(text)
        if not terms:
            return None
        hits = self.retrieve(" ".join(sorted(terms)), limit=1)
        return hits[0] if hits else None

    def _best_folder_for_text(self, text: str) -> str:
        terms = self._query_terms(text)
        if not terms:
            return "Inbox"
        folders = self.folders()
        best_path = "Inbox"
        best_score = 0
        for item in folders:
            folder_path = item.get("path") or ""
            if not folder_path:
                continue
            score = self._match_score(folder_path, terms)
            if score > best_score:
                best_score = score
                best_path = folder_path
        if best_score > 0:
            return best_path
        topic = self._topic_slug(text)
        if topic:
            return f"Projects/{topic}"
        return "Inbox"

    def _topic_slug(self, text: str) -> str:
        words = [w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", text)]
        stop = {"this", "that", "with", "from", "into", "about", "please", "save", "remember", "document", "obsidian", "vault"}
        filtered = [w for w in words if w not in stop]
        if not filtered:
            return ""
        topic = "-".join(filtered[:3])
        return topic[:60].strip("-")

    def _infer_note_name(self, text: str) -> str:
        heading = re.search(r"^\s*#\s+(.+)$", text, flags=re.M)
        if heading:
            title = heading.group(1).strip()
            return f"{self._slug(title)}.md"
        sentence = re.split(r"[.!?\n]", text.strip(), maxsplit=1)[0]
        sentence = re.sub(
            r"^\s*(can you|could you|please|pls|would you|find|look up|save|document|remember)\b[:\s-]*",
            "",
            sentence,
            flags=re.I,
        )
        sentence = re.sub(r"\b(in|into)\s+my\s+(obsidian|vault|notes?)\b", "", sentence, flags=re.I)
        title = " ".join(re.findall(r"[A-Za-z0-9]+", sentence)[:8]).strip()
        if not title:
            return f"{datetime.now():%Y-%m-%d}.md"
        return f"{self._slug(title)}.md"

    def _match_score(self, value: str, terms: set[str]) -> int:
        lower = value.lower()
        return sum(lower.count(term) for term in terms)

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
        return slug or "note"

    def _safe_note_name(self, note: str) -> str:
        name = note.strip()
        if not name:
            name = f"{datetime.now():%Y-%m-%d}.md"
        if "/" in name or "\\" in name:
            name = Path(name).name
        if not name.lower().endswith(".md"):
            name += ".md"
        slugged = self._slug(name[:-3])
        return f"{slugged}.md"
