import tempfile
import unittest
from pathlib import Path

from sankalp.agent import Agent
from sankalp.memory import ObsidianMemory
from sankalp.sessions import SessionStore
from sankalp.tools import ToolRegistry


class FakeLLM:
    def complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
        return {
            "text": f"memory={bool(memory_context)} latest={messages[-1]['content']}",
            "response_id": "resp_test",
        }


class AgentTests(unittest.TestCase):
    def test_remember_routes_to_memory_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            result = agent.turn(None, "remember: I like searchable notes")

            self.assertIn("Remembered", result["message"]["content"])
            self.assertEqual(result["tool_calls"][0]["name"], "memory_remember")

    def test_normal_turn_retrieves_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            memory.capture("Sankalp should use Obsidian for memory.", source="test")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            result = agent.turn(None, "What should Sankalp use for memory?")

            self.assertIn("memory=True", result["message"]["content"])

    def test_turn_passes_attachments_and_options_to_llm(self):
        class CaptureLLM:
            def complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
                self.options = options
                self.attachments = attachments
                return {"text": "ok", "response_id": None}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            llm = CaptureLLM()
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), llm)

            result = agent.turn(None, "summarize", {
                "options": {"provider": "local_openai", "model": "qwen"},
                "attachments": [{"name": "note.md", "kind": "text", "text": "# Hi"}],
            })

            self.assertEqual(result["message"]["content"], "ok")
            self.assertEqual(llm.options["model"], "qwen")
            self.assertEqual(llm.attachments[0]["name"], "note.md")

    def test_edit_index_truncates_conversation_before_resend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())
            first = agent.turn(None, "first question")
            session_id = first["session"]["session_id"]

            result = agent.turn(session_id, "edited question", {"edit_index": 0})

            self.assertEqual(result["messages"][0]["content"], "edited question")
            self.assertEqual(len(result["messages"]), 2)
            self.assertNotIn("first question", result["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
