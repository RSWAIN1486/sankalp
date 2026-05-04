import tempfile
import unittest
from pathlib import Path

from sankalp.agent import Agent
from sankalp.memory import ObsidianMemory
from sankalp.sessions import SessionStore
from sankalp.tools import ToolRegistry


class FakeLLM:
    def complete(self, messages, memory_context, previous_response_id=None):
        return {"text": memory_context, "response_id": None}


class ProfileTests(unittest.TestCase):
    def test_profile_self_section_and_deletable_trait(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ObsidianMemory(Path(tmp))
            memory.save_self_profile("I like calm, direct collaboration.")
            trait_id = memory.add_inferred_trait("The user prefers small steps.", "session:test")

            profile = memory.read_profile()
            self.assertIn("calm", profile["self_profile"])
            self.assertEqual(profile["traits"][0]["id"], trait_id)

            self.assertTrue(memory.delete_trait(trait_id))
            self.assertEqual(memory.read_profile()["traits"], [])

    def test_agent_infers_first_person_trait(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            agent.turn(None, "I prefer concise architecture docs.")

            traits = memory.read_profile()["traits"]
            self.assertTrue(traits)
            self.assertIn("prefers concise architecture docs", traits[0]["text"])


if __name__ == "__main__":
    unittest.main()
