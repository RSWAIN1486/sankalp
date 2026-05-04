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


if __name__ == "__main__":
    unittest.main()
