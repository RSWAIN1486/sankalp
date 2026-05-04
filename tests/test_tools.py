import os
import tempfile
import unittest
from pathlib import Path

from sankalp.memory import ObsidianMemory
from sankalp.tools import ToolRegistry


class ToolTests(unittest.TestCase):
    def test_file_tools_stay_inside_allowed_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("SANKALP_ALLOWED_ROOTS")
            os.environ["SANKALP_ALLOWED_ROOTS"] = tmp
            try:
                tools = ToolRegistry(ObsidianMemory(Path(tmp) / "vault"))
                ok = tools.call("file_append", path="notes/test.md", text="hello")
                blocked = tools.call("file_read", path="/etc/passwd")
            finally:
                if old is None:
                    os.environ.pop("SANKALP_ALLOWED_ROOTS", None)
                else:
                    os.environ["SANKALP_ALLOWED_ROOTS"] = old

            self.assertEqual(ok.status, "ok")
            self.assertEqual(blocked.status, "blocked")

    def test_terminal_is_blocked_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolRegistry(ObsidianMemory(Path(tmp)))
            result = tools.call("terminal", command="echo hi")

            self.assertEqual(result.status, "blocked")

    def test_memory_search_returns_obsidian_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ObsidianMemory(Path(tmp))
            memory.capture("Stripe Radar helps with fraud detection notes.", source="test")
            tools = ToolRegistry(memory)

            result = tools.call("memory_search", query="stripe fraud detection")

            self.assertEqual(result.status, "ok")
            self.assertEqual(result.output["hits"][0]["path"].split("/")[0], "Inbox")
            self.assertIn("Stripe Radar", result.output["hits"][0]["snippet"])


if __name__ == "__main__":
    unittest.main()
