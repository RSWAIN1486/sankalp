import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_file_find_searches_allowed_roots_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("SANKALP_ALLOWED_ROOTS")
            root_a = Path(tmp) / "a"
            root_b = Path(tmp) / "b"
            (root_a / "nested").mkdir(parents=True)
            root_b.mkdir()
            (root_a / "nested" / "invoice_alpha.md").write_text("a", encoding="utf-8")
            (root_b / "invoice_beta").mkdir()
            os.environ["SANKALP_ALLOWED_ROOTS"] = os.pathsep.join([str(root_a), str(root_b)])
            try:
                tools = ToolRegistry(ObsidianMemory(Path(tmp) / "vault"))
                result = tools.call("file_find", query="invoice")
            finally:
                if old is None:
                    os.environ.pop("SANKALP_ALLOWED_ROOTS", None)
                else:
                    os.environ["SANKALP_ALLOWED_ROOTS"] = old

            self.assertEqual(result.status, "ok")
            paths = [item["path"] for item in result.output["matches"]]
            self.assertTrue(any(path.endswith("invoice_alpha.md") for path in paths))
            self.assertTrue(any(path.endswith("invoice_beta") for path in paths))

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
            self.assertTrue(result.output["hits"][0]["path"].endswith(".md"))
            self.assertIn("Stripe Radar", result.output["hits"][0]["snippet"])

    def test_browser_search_parses_results(self):
        class FakeResponse:
            def __init__(self, payload: bytes):
                self._payload = payload

            def read(self, _limit=None):
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        html = b'''
        <html><body>
        <a class="result__a" href="https://example.com/a">Result A</a>
        <a class="result__a" href="https://example.com/b">Result B</a>
        </body></html>
        '''
        with tempfile.TemporaryDirectory() as tmp:
            tools = ToolRegistry(ObsidianMemory(Path(tmp)))
            with patch("urllib.request.urlopen", return_value=FakeResponse(html)):
                result = tools.call("browser_search", query="jepa papers", limit=2)

            self.assertEqual(result.status, "ok")
            self.assertEqual(len(result.output["results"]), 2)
            self.assertEqual(result.output["results"][0]["url"], "https://example.com/a")


if __name__ == "__main__":
    unittest.main()
