import tempfile
import unittest
from pathlib import Path

from sankalp.memory import ObsidianMemory


class MemoryTests(unittest.TestCase):
    def test_capture_appends_to_inbox_and_retrieves(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ObsidianMemory(Path(tmp))
            path = memory.capture("The user prefers append-first memory.", source="test")

            self.assertEqual(path.parent.name, "Inbox")
            self.assertIn("append-first", path.read_text(encoding="utf-8"))

            hits = memory.retrieve("append first memory")
            self.assertTrue(hits)
            self.assertEqual(hits[0].path, str(path.relative_to(Path(tmp))))

    def test_session_note_is_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ObsidianMemory(Path(tmp))
            path = memory.append_session_turn("abc123", "user", "hello")

            text = path.read_text(encoding="utf-8")
            self.assertIn("# Session abc123", text)
            self.assertIn("## User", text)
            self.assertIn("hello", text)

    def test_retrieve_searches_vault_names_and_skips_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "Skills" / "system design").mkdir(parents=True)
            (vault / "Sessions").mkdir()
            note = vault / "Skills" / "system design" / "Stripe Fraud Detection - Radar.md"
            note.write_text("Radar rules, reviews, and disputes notes live here.", encoding="utf-8")
            (vault / "Sessions" / "2026-05-04-chat.md").write_text(
                "stripe fraud detection transient chat transcript",
                encoding="utf-8",
            )

            hits = ObsidianMemory(vault).retrieve("documentation around stripe fraud detection")
            paths = [hit.path for hit in hits]

            self.assertEqual(paths[0], "Skills/system design/Stripe Fraud Detection - Radar.md")
            self.assertNotIn("Sessions/2026-05-04-chat.md", paths)
            self.assertIn("Radar rules", hits[0].text)


if __name__ == "__main__":
    unittest.main()
