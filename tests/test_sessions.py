import tempfile
import unittest
from pathlib import Path

from sankalp.sessions.store import SessionStore, title_from_query


class SessionStoreTests(unittest.TestCase):
    def test_title_from_query_removes_request_prefix(self):
        self.assertEqual(title_from_query("can you check for the latest election results today"), "latest election results today")

    def test_rename_and_delete_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            session = store.create()

            renamed = store.rename(session.session_id, "Project Radar")
            deleted = store.delete(session.session_id)

            self.assertEqual(renamed.title, "Project Radar")
            self.assertTrue(deleted)
            self.assertEqual(store.list(), [])

    def test_generated_title_does_not_replace_manual_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            session = store.create()

            store.rename(session.session_id, "Manual Title")
            updated = store.update_generated_title(session.session_id, "AI Title")

            self.assertEqual(updated.title, "Manual Title")
            self.assertEqual(updated.title_source, "manual")

    def test_truncate_messages_removes_branch_and_tool_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            session = store.create()
            session.messages = [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ]
            session.tool_calls = [{"name": "memory_search", "status": "ok"}]
            session.previous_response_id = "resp_123"
            store.save(session)

            truncated = store.truncate_messages(session.session_id, 1)

            self.assertEqual(truncated.messages, [{"role": "user", "content": "one"}])
            self.assertEqual(truncated.tool_calls, [])
            self.assertIsNone(truncated.previous_response_id)


if __name__ == "__main__":
    unittest.main()
