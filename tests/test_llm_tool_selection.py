import unittest

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


if __name__ == "__main__":
    unittest.main()
