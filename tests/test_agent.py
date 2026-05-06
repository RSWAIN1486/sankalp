import tempfile
import unittest
from pathlib import Path

from sankalp.agent import Agent
import sankalp.agent.llm as llm_module
from sankalp.agent.llm import LLMAdapter
from sankalp.memory import ObsidianMemory
from sankalp.sessions import SessionStore
from sankalp.tools import ToolRegistry


class FakeLLM:
    def complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
        return {
            "text": f"memory={bool(memory_context)} latest={messages[-1]['content']}",
            "response_id": "resp_test",
        }

    def select_tool(self, message, tools, options=None):
        return None

    def memory_search_query(self, message, options=None):
        return None

    def stream_complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
        yield {"type": "reasoning", "text": "planning"}
        yield {"type": "delta", "text": "hello "}
        yield {"type": "delta", "text": "world"}
        yield {"type": "response_id", "response_id": "resp_stream"}


class AgentTests(unittest.TestCase):
    def test_llm_prompt_reads_soul_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_soul = llm_module.SOUL_FILE
            soul = Path(tmp) / "SOUL.md"
            soul.write_text("# Persona\n\nBe concise and kind.\n", encoding="utf-8")
            try:
                llm_module.SOUL_FILE = soul
                prompt = LLMAdapter()._developer_prompt("")
            finally:
                llm_module.SOUL_FILE = old_soul

            self.assertIn("Agent persona", prompt)
            self.assertIn("Be concise and kind.", prompt)

    def test_remember_routes_to_memory_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            result = agent.turn(None, "/remember I like searchable notes")

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

    def test_memory_lookup_routes_to_search_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            memory.capture("Stripe Radar is the fraud detection note.", source="test")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            result = agent.turn(None, "do you see any documentation around stripe fraud detection in my memory")

            self.assertEqual(result["tool_calls"][0]["name"], "memory_search")
            self.assertIn("Yes, I found relevant notes", result["message"]["content"])
            self.assertIn("What would you like to know", result["message"]["content"])

    def test_memory_lookup_can_only_confirm_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            memory.capture("Project Alpha deployment note.", source="test")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            result = agent.turn(None, "check memory for project alpha")

            self.assertIn("Yes, I found relevant notes", result["message"]["content"])
            self.assertIn("What would you like to know", result["message"]["content"])
            self.assertNotIn("Project Alpha deployment note.", result["message"]["content"])

    def test_llm_can_select_memory_search_when_regex_misses(self):
        class RouterLLM(FakeLLM):
            def select_tool(self, message, tools, options=None):
                return {"tool": "memory_search", "arguments": {"query": "stripe radar"}}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            memory.capture("Stripe Radar review lives in this vault.", source="test")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), RouterLLM())

            result = agent.turn(None, "anything saved about radar?")

            self.assertEqual(result["tool_calls"][0]["name"], "memory_search")
            self.assertIn("Yes, I found relevant notes", result["message"]["content"])

    def test_memory_lookup_answers_specific_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            memory.capture("Project Alpha uses deterministic matching.", source="test")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            result = agent.turn(None, "what method does project alpha use?")

            self.assertIn("memory=True", result["message"]["content"])

    def test_memory_lookup_matches_note_path_and_ignores_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            (vault / "Skills" / "system design").mkdir(parents=True)
            (vault / "Sessions").mkdir(parents=True)
            (vault / "Skills" / "system design" / "Stripe Fraud Detection - Radar.md").write_text(
                "Use Radar rules and manual review notes.",
                encoding="utf-8",
            )
            (vault / "Sessions" / "2026-05-04-chat.md").write_text(
                "stripe fraud detection chat transcript",
                encoding="utf-8",
            )
            memory = ObsidianMemory(vault)
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            result = agent.turn(None, "do you see any documentation around stripe fraud detection in my memory")
            hit_paths = [hit["path"] for hit in result["tool_calls"][0]["output"]["hits"]]

            self.assertIn("Skills/system design/Stripe Fraud Detection - Radar.md", hit_paths)
            self.assertNotIn("Sessions/2026-05-04-chat.md", hit_paths)

    def test_memory_lookup_uses_llm_rewritten_query(self):
        class QueryLLM(FakeLLM):
            def memory_search_query(self, message, options=None):
                return "stripe fraud detection radar"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            memory.capture("Stripe Radar fraud detection note.", source="test")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), QueryLLM())

            result = agent.turn(None, "can you check my memory about that payments risk thing")
            tool_input = result["tool_calls"][0]["input"]

            self.assertEqual(tool_input["query"], "stripe fraud detection radar")
            self.assertEqual(tool_input["original_query"], "can you check my memory about that payments risk thing")

    def test_llm_tool_selection_none_falls_back_to_chat(self):
        class RouterLLM(FakeLLM):
            def select_tool(self, message, tools, options=None):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), RouterLLM())

            result = agent.turn(None, "hello there")

            self.assertEqual(result["tool_calls"], [])
            self.assertIn("latest=hello there", result["message"]["content"])

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

    def test_turn_stream_emits_reasoning_and_deltas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            events = list(agent.turn_stream(None, "hello"))
            event_names = [event["event"] for event in events]
            self.assertIn("reasoning", event_names)
            self.assertIn("delta", event_names)
            self.assertEqual(events[-1]["event"], "done")
            self.assertEqual(events[-1]["data"]["message"]["content"], "hello world")


if __name__ == "__main__":
    unittest.main()
