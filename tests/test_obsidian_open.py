import tempfile
import unittest
from pathlib import Path

from sankalp.memory import ObsidianMemory


class ObsidianOpenTests(unittest.TestCase):
    def test_children_and_open_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "Obsidian Vault"
            (vault / "Projects" / "Bluestone").mkdir(parents=True)
            note = vault / "Projects" / "Bluestone" / "Discussion points.md"
            note.write_text("hello", encoding="utf-8")

            memory = ObsidianMemory(vault)
            children = memory.children("Projects")
            folder_open = memory.open_target("Projects/Bluestone")
            note_open = memory.open_target("Projects/Bluestone/Discussion points.md")

            self.assertEqual(children["items"][0]["type"], "directory")
            self.assertEqual(folder_open["mode"], "finder")
            self.assertEqual(note_open["mode"], "obsidian")
            self.assertIn("obsidian://open", note_open["uri"])


if __name__ == "__main__":
    unittest.main()
