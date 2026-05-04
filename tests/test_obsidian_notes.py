import tempfile
import unittest
from pathlib import Path

from sankalp.memory import ObsidianMemory


class ObsidianNotesTests(unittest.TestCase):
    def test_notes_returns_recursive_previews(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "Notes" / "Nested").mkdir(parents=True)
            (vault / "Notes" / "Root.md").write_text("root preview", encoding="utf-8")
            (vault / "Notes" / "Nested" / "Child.md").write_text("child preview", encoding="utf-8")

            result = ObsidianMemory(vault).notes("Notes")
            paths = {note["path"] for note in result["notes"]}

            self.assertEqual(result["error"], None)
            self.assertIn("Notes/Root.md", paths)
            self.assertIn("Notes/Nested/Child.md", paths)


if __name__ == "__main__":
    unittest.main()
