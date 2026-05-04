import json
import os
import unittest
import urllib.request
from unittest.mock import patch

from sankalp.agent.llm import LLMAdapter


class LLMToolSelectionTests(unittest.TestCase):
    def test_parse_tool_selection_accepts_json(self):
        result = LLMAdapter()._parse_tool_selection(
            '{"tool":"memory_search","arguments":{"query":"stripe radar"}}',
            {"memory_search"},
        )

        self.assertEqual(result["tool"], "memory_search")
        self.assertEqual(result["arguments"]["query"], "stripe radar")

    def test_parse_tool_selection_rejects_unknown_tool(self):
        result = LLMAdapter()._parse_tool_selection(
            '{"tool":"terminal","arguments":{"command":"ls"}}',
            {"memory_search"},
        )

        self.assertIsNone(result)

    def test_parse_tool_selection_handles_fenced_json(self):
        result = LLMAdapter()._parse_tool_selection(
            '```json\n{"tool":"file_read","arguments":{"path":"README.md"}}\n```',
            {"file_read"},
        )

        self.assertEqual(result["tool"], "file_read")
        self.assertEqual(result["arguments"]["path"], "README.md")

    def test_parse_memory_search_query_accepts_json(self):
        result = LLMAdapter()._parse_memory_search_query(
            '```json\n{"query":"stripe fraud detection radar algorithm"}\n```'
        )

        self.assertEqual(result, "stripe fraud detection radar algorithm")

    def test_parse_memory_search_query_rejects_empty_query(self):
        result = LLMAdapter()._parse_memory_search_query('{"query":""}')

        self.assertIsNone(result)

    def test_openai_provider_can_rewrite_memory_search_query(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"output_text": "{\"query\":\"stripe radar algorithm\"}"}).encode("utf-8")

        def fake_urlopen(request, timeout=60):
            return FakeResponse()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            old = urllib.request.urlopen
            urllib.request.urlopen = fake_urlopen
            try:
                result = LLMAdapter().memory_search_query(
                    "can you check what was the algorithm used for fraud detection in Stripe from my memory",
                    {"provider": "openai", "model": "gpt-test"},
                )
            finally:
                urllib.request.urlopen = old

        self.assertEqual(result, "stripe radar algorithm")


if __name__ == "__main__":
    unittest.main()
