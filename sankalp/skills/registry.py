from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sankalp.config import SKILLS_DIR


BUNDLED_SKILLS_DIR = Path(__file__).resolve().parent / "bundled"


@dataclass
class Skill:
    id: str
    name: str
    description: str
    path: str
    entrypoint: str
    category: str = ""
    version: str = "0.1.0"
    commands: list[str] | None = None
    triggers: list[str] | None = None
    requires: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["commands"] = data["commands"] or []
        data["triggers"] = data["triggers"] or []
        data["requires"] = data["requires"] or {}
        return data


def seed_builtin_skills(skills_dir: Path = SKILLS_DIR, bundled_dir: Path = BUNDLED_SKILLS_DIR) -> None:
    if not bundled_dir.exists():
        return
    skills_dir.mkdir(parents=True, exist_ok=True)
    for manifest in bundled_dir.rglob("skill.json"):
        relative_dir = manifest.parent.relative_to(bundled_dir)
        target = skills_dir / relative_dir
        if target.exists():
            continue
        shutil.copytree(manifest.parent, target)


class SkillRegistry:
    def __init__(self, skills_dir: Path = SKILLS_DIR):
        self.skills_dir = skills_dir

    def list(self) -> list[Skill]:
        if not self.skills_dir.exists():
            return []
        skills = [self._load_skill(manifest) for manifest in sorted(self.skills_dir.rglob("skill.json"))]
        return [skill for skill in skills if skill is not None]

    def capabilities(self) -> list[dict[str, Any]]:
        return [skill.to_dict() for skill in self.list()]

    def _load_skill(self, manifest_path: Path) -> Skill | None:
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        entrypoint = str(data.get("entrypoint") or "SKILL.md").strip()
        skill_dir = manifest_path.parent
        if not (skill_dir / entrypoint).is_file():
            return None

        relative = skill_dir.relative_to(self.skills_dir)
        category = str(data.get("category") or (relative.parts[0] if len(relative.parts) > 1 else "")).strip()
        skill_id = str(data.get("id") or ".".join(relative.parts)).strip()
        name = str(data.get("name") or relative.name).strip()
        description = str(data.get("description") or self._description_from_file(skill_dir)).strip()
        if not skill_id or not name:
            return None

        return Skill(
            id=skill_id,
            name=name,
            description=description,
            path=str(relative),
            entrypoint=entrypoint,
            category=category,
            version=str(data.get("version") or "0.1.0"),
            commands=[str(item) for item in data.get("commands") or []],
            triggers=[str(item) for item in data.get("triggers") or []],
            requires=dict(data.get("requires") or {}),
        )

    def _description_from_file(self, skill_dir: Path) -> str:
        description = skill_dir / "DESCRIPTION.md"
        if not description.is_file():
            return ""
        lines = [line.strip() for line in description.read_text(encoding="utf-8").splitlines()]
        return next((line.lstrip("# ").strip() for line in lines if line and not line.startswith("<!--")), "")
