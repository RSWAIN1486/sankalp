import tempfile
import unittest
from pathlib import Path

from sankalp.memory import ObsidianMemory


class ObsidianWorkspaceTests(unittest.TestCase):
    def test_tree_and_recent_notes_can_scope_to_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "Projects" / "Bluestone").mkdir(parents=True)
            (vault / "Projects" / "Bluestone" / "Discussion points.md").write_text("hello", encoding="utf-8")
            (vault / "Notes").mkdir()
            (vault / "Notes" / "Other.md").write_text("outside", encoding="utf-8")

            memory = ObsidianMemory(vault, workspace="Projects/Bluestone")
            tree = memory.tree()
            recent = memory.list_recent()

            self.assertIsNone(tree["error"])
            self.assertEqual(tree["items"][0]["name"], "Discussion points.md")
            self.assertEqual(recent[0]["path"], "Projects/Bluestone/Discussion points.md")
            self.assertNotIn("Other.md", [note["path"] for note in recent])

    def test_folders_lists_only_top_level_workspace_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "Notes" / "Nested").mkdir(parents=True)
            (vault / "Projects" / "Bluestone").mkdir(parents=True)
            (vault / ".obsidian" / "themes").mkdir(parents=True)

            folders = ObsidianMemory(vault).folders()
            paths = [folder["path"] for folder in folders]

            self.assertIn("Notes", paths)
            self.assertIn("Projects", paths)
            self.assertNotIn("Notes/Nested", paths)
            self.assertNotIn("Projects/Bluestone", paths)
            self.assertNotIn(".obsidian", paths)


if __name__ == "__main__":
    unittest.main()
