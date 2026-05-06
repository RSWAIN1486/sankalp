import json
import tempfile
import unittest
from pathlib import Path

from sankalp.skills.registry import SkillRegistry, seed_builtin_skills


class SkillRegistryTests(unittest.TestCase):
    def test_loads_skill_manifest_from_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "note-taking" / "obsidian"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# Obsidian\n", encoding="utf-8")
            (skill_dir / "skill.json").write_text(
                json.dumps({
                    "id": "note-taking.obsidian",
                    "name": "Obsidian",
                    "description": "Use Obsidian memory.",
                    "commands": ["/remember"],
                    "entrypoint": "SKILL.md",
                }),
                encoding="utf-8",
            )

            skills = SkillRegistry(root).capabilities()

            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0]["id"], "note-taking.obsidian")
            self.assertEqual(skills[0]["path"], "note-taking/obsidian")
            self.assertEqual(skills[0]["commands"], ["/remember"])

    def test_seeds_bundled_skills_without_overwriting_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            bundled = Path(tmp) / "bundled"
            bundled_skill = bundled / "note-taking" / "obsidian"
            bundled_skill.mkdir(parents=True)
            (bundled_skill / "SKILL.md").write_text("# Bundled\n", encoding="utf-8")
            (bundled_skill / "skill.json").write_text(
                json.dumps({"id": "note-taking.obsidian", "name": "Obsidian"}),
                encoding="utf-8",
            )

            seed_builtin_skills(target, bundled)
            (target / "note-taking" / "obsidian" / "SKILL.md").write_text("# User edited\n", encoding="utf-8")
            seed_builtin_skills(target, bundled)

            self.assertEqual((target / "note-taking" / "obsidian" / "SKILL.md").read_text(encoding="utf-8"), "# User edited\n")


if __name__ == "__main__":
    unittest.main()
