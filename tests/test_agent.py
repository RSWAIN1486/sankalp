import tempfile
import unittest
from pathlib import Path

from sankalp.agent import Agent
from sankalp.memory import ObsidianMemory
from sankalp.sessions import SessionStore
from sankalp.tools import ToolRegistry


class FakeLLM:
    def complete(self, messages, memory_context, previous_response_id=None):
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


if __name__ == "__main__":
    unittest.main()
