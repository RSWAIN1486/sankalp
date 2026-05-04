import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sankalp.agent.llm import LLMAdapter


class CodexAdapterTests(unittest.TestCase):
    def test_codex_exec_uses_supported_noninteractive_flags(self):
        seen = {}

        def fake_run(command, input, text, capture_output, timeout):
            seen["command"] = command
            output_path = command[command.index("--output-last-message") + 1]
            with open(output_path, "w", encoding="utf-8") as handle:
                handle.write("hello")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("sankalp.agent.llm.subprocess.run", side_effect=fake_run):
            result = LLMAdapter()._codex(
                {"codex_model": "gpt-5.4-mini"},
                [{"role": "user", "content": "hi"}],
                "",
            )

        self.assertEqual(result["text"], "hello")
        self.assertIn("exec", seen["command"])
        self.assertIn("--sandbox", seen["command"])
        self.assertNotIn("--ask-for-approval", seen["command"])
        self.assertIn("gpt-5.4-mini", seen["command"])


if __name__ == "__main__":
    unittest.main()
