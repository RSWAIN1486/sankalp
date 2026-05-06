import unittest
from types import SimpleNamespace
from unittest.mock import patch
from io import StringIO

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

    def test_codex_stream_parses_json_delta_events(self):
        class FakePopen:
            def __init__(self, *args, **kwargs):
                self.command = args[0]
                self.stdin = StringIO()
                self.stdout = StringIO(
                    '{"type":"response.output_text.delta","delta":"hello "}\n'
                    '{"type":"response.output_text.delta","delta":"codex"}\n'
                )
                self.stderr = StringIO("")
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return 0

            def kill(self):
                return None

        with patch("sankalp.agent.llm.subprocess.Popen", side_effect=FakePopen):
            chunks = list(LLMAdapter()._codex_stream({"codex_model": "gpt-5.4-mini"}, [{"role": "user", "content": "hi"}], ""))
        deltas = [item["text"] for item in chunks if item.get("type") == "delta"]
        self.assertEqual("".join(deltas), "hello codex")
        self.assertEqual(chunks[-1]["type"], "response_id")

    def test_codex_stream_extracts_message_content_parts(self):
        class FakePopen:
            def __init__(self, *args, **kwargs):
                self.command = args[0]
                self.stdin = StringIO()
                self.stdout = StringIO(
                    '{"type":"response.completed","message":{"content":[{"type":"output_text","text":"hello from parts"}]}}\n'
                )
                self.stderr = StringIO("")
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return 0

            def kill(self):
                return None

        with patch("sankalp.agent.llm.subprocess.Popen", side_effect=FakePopen):
            chunks = list(LLMAdapter()._codex_stream({"codex_model": "gpt-5.4-mini"}, [{"role": "user", "content": "hi"}], ""))
        deltas = [item["text"] for item in chunks if item.get("type") == "delta"]
        self.assertEqual("".join(deltas), "hello from parts")


if __name__ == "__main__":
    unittest.main()
