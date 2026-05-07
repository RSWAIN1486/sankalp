import tempfile
import unittest
from pathlib import Path

from sankalp.memory import ObsidianMemory


class MemoryTests(unittest.TestCase):
    def test_capture_routes_to_best_folder_and_retrieves(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "Research").mkdir(parents=True)
            memory = ObsidianMemory(vault)
            path = memory.capture("The user prefers append-first memory.", source="test")

            self.assertEqual(path.parent.parent.name, "Projects")
            self.assertIn("append-first", path.read_text(encoding="utf-8"))

            hits = memory.retrieve("append first memory")
            self.assertTrue(hits)
            self.assertEqual(hits[0].path, str(path.resolve().relative_to(Path(tmp).resolve())))

    def test_capture_uses_explicit_folder_and_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ObsidianMemory(Path(tmp))
            content = "folder: Research/JEPA\nnote: papers.md\n\nV-JEPA reading notes."

            path = memory.capture(content, source="test")

            self.assertEqual(path.name, "papers.md")
            self.assertEqual(str(path.parent.resolve().relative_to(Path(tmp).resolve())), "Research/JEPA")
            self.assertIn("V-JEPA", path.read_text(encoding="utf-8"))

    def test_folder_paths_lists_nested_non_session_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "Research" / "JEPA").mkdir(parents=True)
            (vault / "Sessions" / "Internal").mkdir(parents=True)
            memory = ObsidianMemory(vault)

            paths = memory.folder_paths()

            self.assertIn("Research", paths)
            self.assertIn("Research/JEPA", paths)
            self.assertNotIn("Sessions/Internal", paths)

    def test_session_note_is_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ObsidianMemory(Path(tmp))
            path = memory.append_session_turn("abc123", "user", "hello")

            text = path.read_text(encoding="utf-8")
            self.assertIn("# Session abc123", text)
            self.assertIn("## User", text)
            self.assertIn("hello", text)

    def test_delete_session_notes_removes_matching_transcripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ObsidianMemory(Path(tmp))
            first = memory.append_session_turn("abc123abc123", "user", "hello")
            second = memory.append_session_turn("abc123abc123", "assistant", "hi")
            other = memory.append_session_turn("def456def456", "user", "keep")

            deleted = memory.delete_session_notes("abc123abc123")

            self.assertEqual(deleted, 1)
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            self.assertTrue(other.exists())

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

    def test_retrieve_filters_weak_distractors(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "system design").mkdir(parents=True)
            (vault / "LLM").mkdir()
            (vault / "system design" / "Stripe Fraud Detection - Radar.md").write_text(
                "Stripe fraud detection used XGBoost and a DNN before Shield NeXt.",
                encoding="utf-8",
            )
            (vault / "LLM" / "Open Source LLM Architectures.md").write_text(
                "Algorithm notes about unrelated model architectures.",
                encoding="utf-8",
            )

            hits = ObsidianMemory(vault).retrieve("what was the algorithm used for fraud detection in stripe")
            paths = [hit.path for hit in hits]

            self.assertEqual(paths, ["system design/Stripe Fraud Detection - Radar.md"])


if __name__ == "__main__":
    unittest.main()
