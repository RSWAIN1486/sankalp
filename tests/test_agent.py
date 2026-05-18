import os
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

    def memory_save_target(self, request, content, folders, existing_notes, options=None):
        return None


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
            self.assertIn(".md", result["message"]["content"])
            self.assertEqual(result["tool_calls"][0]["name"], "memory_remember")

    def test_obsidian_save_request_routes_without_slash_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())
            first = agent.turn(None, "JEPA summary content")
            session_id = first["session"]["session_id"]

            result = agent.turn(session_id, "please document that in my obsidian vault")

            self.assertIn("Saved to Obsidian", result["message"]["content"])
            self.assertEqual(result["tool_calls"][-1]["name"], "memory_remember")

    def test_plain_save_it_routes_to_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())
            first = agent.turn(None, "Important JEPA findings summary")
            session_id = first["session"]["session_id"]

            result = agent.turn(session_id, "save it")

            self.assertIn("Saved to Obsidian", result["message"]["content"])
            self.assertEqual(result["tool_calls"][-1]["name"], "memory_remember")

    def test_save_uses_llm_suggested_folder_and_note(self):
        class SaveTargetLLM(FakeLLM):
            def memory_save_target(self, request, content, folders, existing_notes, options=None):
                return {"folder": "Research", "note": "jepa-papers.md"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), SaveTargetLLM())
            first = agent.turn(None, "JEPA findings summary")
            session_id = first["session"]["session_id"]

            result = agent.turn(session_id, "document it")
            text = result["message"]["content"]
            tool_input = result["tool_calls"][-1]["input"]

            self.assertIn("Research/jepa-papers.md", text)
            self.assertEqual(tool_input["folder"], "Research")
            self.assertEqual(tool_input["note"], "jepa-papers.md")

    def test_research_and_document_saves_answer_not_prompt(self):
        class ResearchLLM(FakeLLM):
            def complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
                return {
                    "text": "Top JEPA papers: I-JEPA, V-JEPA, V-JEPA 2.",
                    "response_id": "resp_test",
                }

            def memory_save_target(self, request, content, folders, existing_notes, options=None):
                return {"folder": "Research", "note": "jepa-papers.md"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), ResearchLLM())

            result = agent.turn(None, "can you find the latest papers on JEPA and their details and document them in my obsidian")

            self.assertIn("Top JEPA papers", result["message"]["content"])
            self.assertIn("Saved to Obsidian at `Research/jepa-papers.md`.", result["message"]["content"])
            saved = (root / "vault" / "Research" / "jepa-papers.md").read_text(encoding="utf-8")
            self.assertIn("Top JEPA papers", saved)

    def test_research_save_extracts_note_draft_and_routes_to_research(self):
        class ResearchLLM(FakeLLM):
            def complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
                return {
                    "text": (
                        "Here are the conversational findings.\n\n"
                        "**Obsidian Note Draft**\n\n"
                        "```markdown\n"
                        "# Latest JEPA Papers\n\n"
                        "## Summary\n"
                        "Only this clean note body should be saved.\n"
                        "```\n\n"
                        "Research provider: `firecrawl:self-hosted`"
                    ),
                    "response_id": "resp_test",
                }

            def memory_save_target(self, request, content, folders, existing_notes, options=None):
                return {"folder": "Inbox", "note": "latest-jepa-papers.md"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            (vault / "Research").mkdir(parents=True)
            memory = ObsidianMemory(vault)
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), ResearchLLM())

            result = agent.turn(None, "can you find the latest papers on JEPA and their details and document them in my obsidian")

            self.assertIn("Saved to Obsidian at `Research/latest-jepa-papers.md`.", result["message"]["content"])
            saved = (vault / "Research" / "latest-jepa-papers.md").read_text(encoding="utf-8")
            self.assertIn("# Latest JEPA Papers", saved)
            self.assertIn("Only this clean note body should be saved.", saved)
            self.assertNotIn("Here are the conversational findings.", saved)
            self.assertNotIn("Obsidian Note Draft", saved)
            self.assertFalse((vault / "Inbox" / "latest-jepa-papers.md").exists())

    def test_auto_save_uses_llm_prepared_memory_save_plan(self):
        class SavePlannerLLM(FakeLLM):
            def complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
                return {
                    "text": (
                        "I found useful source context and drafted the Obsidian note for "
                        "`ML&Agents/Concepts/Grouped Query Attention vs Multi-Head Latent Attention.md`:\n\n"
                        "---\n"
                        "title: Grouped Query Attention vs Multi-Head Latent Attention\n"
                        "---\n\n"
                        "# Grouped Query Attention vs Multi-Head Latent Attention\n\n"
                        "Clean note body."
                    ),
                    "response_id": "resp_test",
                }

            def prepare_memory_save(self, request, answer, folders, existing_notes, options=None):
                return {
                    "folder": "ML&Agents/Concepts",
                    "note": "Grouped Query Attention vs Multi-Head Latent Attention.md",
                    "content": (
                        "---\n"
                        "title: Grouped Query Attention vs Multi-Head Latent Attention\n"
                        "---\n\n"
                        "# Grouped Query Attention vs Multi-Head Latent Attention\n\n"
                        "Clean note body."
                    ),
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            (vault / "ML&Agents" / "Concepts").mkdir(parents=True)
            memory = ObsidianMemory(vault)
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), SavePlannerLLM())

            result = agent.turn(None, "Search and document these concepts - Group query attention vs Multi Head latent attention under ML&Agents/Concepts in obsidian")

            self.assertIn(
                "Saved to Obsidian at `ML&Agents/Concepts/grouped-query-attention-vs-multi-head-latent-attention.md`.",
                result["message"]["content"],
            )
            saved = vault / "ML&Agents" / "Concepts" / "grouped-query-attention-vs-multi-head-latent-attention.md"
            self.assertTrue(saved.exists())
            text = saved.read_text(encoding="utf-8")
            self.assertIn("Clean note body.", text)
            self.assertNotIn("I found useful source context", text)
            self.assertFalse((vault / "Inbox" / "grouped-query-attention-vs-multi-head-latent-attention.md").exists())

    def test_prepared_save_plan_normalizes_fuzzy_folder_to_existing_path(self):
        class SavePlannerLLM(FakeLLM):
            def complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
                return {
                    "text": "# Test Concept\n\nClean note body.",
                    "response_id": "resp_test",
                }

            def prepare_memory_save(self, request, answer, folders, existing_notes, options=None):
                return {
                    "folder": "ML Concepts",
                    "note": "Test Concept.md",
                    "content": "# Test Concept\n\nClean note body.",
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            (vault / "ML&Agents" / "Concepts").mkdir(parents=True)
            memory = ObsidianMemory(vault)
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), SavePlannerLLM())

            result = agent.turn(None, "Search and document test concept under ML concepts in obsidian")

            self.assertIn("Saved to Obsidian at `ML&Agents/Concepts/test-concept.md`.", result["message"]["content"])
            self.assertTrue((vault / "ML&Agents" / "Concepts" / "test-concept.md").exists())
            self.assertFalse((vault / "ML Concepts" / "test-concept.md").exists())

    def test_search_and_document_prefers_web_research_over_memory_lookup(self):
        class SavePlannerLLM(FakeLLM):
            def complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
                return {
                    "text": "# KV Cache Attention Mechanisms Since 2022\n\nWeb-researched synthesis.",
                    "response_id": "resp_test",
                }

            def prepare_memory_save(self, request, answer, folders, existing_notes, options=None):
                return {
                    "folder": "ML Concepts",
                    "note": "KV Cache Attention Mechanisms Since 2022.md",
                    "content": "# KV Cache Attention Mechanisms Since 2022\n\nWeb-researched synthesis.",
                }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            (vault / "ML&Agents" / "Concepts").mkdir(parents=True)
            (vault / "ML&Agents" / "Concepts" / "kv-cache-attention-mechanisms-since-2022.md").write_text(
                "# Existing Note\n\nOld memory hit.",
                encoding="utf-8",
            )
            memory = ObsidianMemory(vault)
            tools = ToolRegistry(memory)

            def fake_browser_search(query, limit=5, include_content=True):
                from sankalp.tools.base import ToolResult

                return ToolResult.run(
                    "browser_search",
                    {"query": query, "limit": limit, "include_content": include_content},
                    {
                        "engine": "test",
                        "results": [{
                            "title": "KV cache attention survey",
                            "url": "https://example.test/kv-cache",
                            "description": "GQA, MLA, KV quantization, and related mechanisms.",
                            "markdown": "GQA, MLA, KV quantization, and cross-layer KV sharing reduce inference memory.",
                        }],
                    },
                )

            tools.browser_search = fake_browser_search
            agent = Agent(SessionStore(root / "sessions"), memory, tools, SavePlannerLLM())

            result = agent.turn(
                None,
                "search about the different attention mechanisms used since 2022 from the first GPT models till today that have improved KV caching memory during inference and document it under ML concepts",
            )

            self.assertEqual(result["tool_calls"][0]["name"], "browser_search")
            self.assertEqual(result["tool_calls"][-1]["name"], "memory_remember")
            self.assertTrue((vault / "ML&Agents" / "Concepts" / "kv-cache-attention-mechanisms-since-2022.md").exists())
            self.assertIn("Saved to Obsidian at `ML&Agents/Concepts/kv-cache-attention-mechanisms-since-2022.md`.", result["message"]["content"])

    def test_save_target_without_llm_prefers_relevant_existing_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            (vault / "Research").mkdir(parents=True)
            memory = ObsidianMemory(vault)
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            target = agent._memory_save_target(
                "find latest JEPA papers and document them",
                "# Latest JEPA Papers\n\nSources from arXiv research papers.",
                {},
            )

            self.assertEqual(target["folder"], "Research")
            self.assertEqual(target["note"], "latest-jepa-papers.md")

    def test_save_target_creates_new_folder_when_no_existing_folder_fits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), FakeLLM())

            target = agent._memory_save_target(
                "document sourdough starter feeding schedule",
                "# Sourdough Starter Feeding Schedule\n\nWeekly maintenance notes.",
                {},
            )

            self.assertEqual(target["folder"], "Sourdough Starter Feeding Schedule")
            self.assertEqual(target["note"], "sourdough-starter-feeding-schedule.md")

    def test_stream_research_and_document_saves_answer(self):
        class ResearchLLM(FakeLLM):
            def complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
                return {"text": "Streamed JEPA findings [1].", "response_id": "resp_test"}

            def memory_save_target(self, request, content, folders, existing_notes, options=None):
                return {"folder": "Research", "note": "streamed-jepa.md"}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), ResearchLLM())

            def fake_search(name, **kwargs):
                from sankalp.tools.base import ToolResult
                if name == "browser_search":
                    return ToolResult.run(
                        "browser_search",
                        {"query": kwargs.get("query"), "limit": kwargs.get("limit")},
                        {"engine": "test", "results": [{"title": "A", "url": "https://example.com", "markdown": "Source body"}]},
                    )
                return ToolRegistry(memory).call(name, **kwargs)

            agent.tools.call = fake_search  # type: ignore[method-assign]
            events = list(agent.turn_stream(None, "find latest JEPA papers and document them in my obsidian"))
            final_text = events[-1]["data"]["message"]["content"]

            self.assertIn("Saved to Obsidian at `Research/streamed-jepa.md`.", final_text)
            saved = (root / "vault" / "Research" / "streamed-jepa.md").read_text(encoding="utf-8")
            self.assertIn("Streamed JEPA findings", saved)

    def test_research_command_routes_to_browser_search_tool(self):
        class ResearchAnswerLLM(FakeLLM):
            def complete(self, messages, memory_context, previous_response_id=None, options=None, attachments=None):
                return {"text": "Summarized result [1]\n\nSources:\n[1] A - https://example.com", "response_id": None}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = ObsidianMemory(root / "vault")
            agent = Agent(SessionStore(root / "sessions"), memory, ToolRegistry(memory), ResearchAnswerLLM())

            def fake_search(name, **kwargs):
                from sankalp.tools.base import ToolResult
                return ToolResult.run(
                    "browser_search",
                    {"query": kwargs.get("query"), "limit": kwargs.get("limit")},
                    {"engine": "test", "results": [{"title": "A", "url": "https://example.com", "markdown": "Source body"}]},
                )

            agent.tools.call = fake_search  # type: ignore[method-assign]
            result = agent.turn(None, "/research latest jepa papers")

            self.assertIn("Summarized result", result["message"]["content"])
            self.assertIn("Research provider: `test`", result["message"]["content"])

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

    def test_natural_file_list_request_uses_agentic_tool_loop(self):
        class PlannerLLM:
            def __init__(self):
                self.calls = 0

            def agent_next_action(self, message, tools, observations, options=None):
                self.calls += 1
                if not observations:
                    return {"action": "tool", "tool": "file_list", "arguments": {"path": "."}}
                return {"action": "answer", "answer": "I found Projects and notes.md."}

            def complete(self, *args, **kwargs):
                raise RuntimeError("model should not be called")

            def select_tool(self, *args, **kwargs):
                raise RuntimeError("selector should not be called")

        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("SANKALP_ALLOWED_ROOTS")
            root = Path(tmp)
            (root / "Projects").mkdir()
            (root / "notes.md").write_text("hello", encoding="utf-8")
            os.environ["SANKALP_ALLOWED_ROOTS"] = str(root)
            try:
                memory = ObsidianMemory(root / "vault")
                tools = ToolRegistry(memory)
                agent = Agent(SessionStore(root / "sessions"), memory, tools, PlannerLLM())
                result = agent.turn(None, "What folders do you see on my system?")
            finally:
                if old is None:
                    os.environ.pop("SANKALP_ALLOWED_ROOTS", None)
                else:
                    os.environ["SANKALP_ALLOWED_ROOTS"] = old

            self.assertEqual(result["tool_calls"][0]["name"], "file_list")
            self.assertIn("Projects", result["message"]["content"])

    def test_ls_command_lists_requested_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("SANKALP_ALLOWED_ROOTS")
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "README.md").write_text("hello", encoding="utf-8")
            os.environ["SANKALP_ALLOWED_ROOTS"] = str(root)
            try:
                memory = ObsidianMemory(root / "vault")
                tools = ToolRegistry(memory)
                agent = Agent(SessionStore(root / "sessions"), memory, tools, FakeLLM())
                result = agent.turn(None, f"/ls {workspace}")
            finally:
                if old is None:
                    os.environ.pop("SANKALP_ALLOWED_ROOTS", None)
                else:
                    os.environ["SANKALP_ALLOWED_ROOTS"] = old

            self.assertEqual(result["tool_calls"][0]["name"], "file_list")
            self.assertIn("README.md", result["message"]["content"])

    def test_find_command_searches_allowed_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("SANKALP_ALLOWED_ROOTS")
            root = Path(tmp)
            workspace = root / "workspace"
            (workspace / "deep").mkdir(parents=True)
            (workspace / "deep" / "roadmap.md").write_text("hello", encoding="utf-8")
            os.environ["SANKALP_ALLOWED_ROOTS"] = str(workspace)
            try:
                memory = ObsidianMemory(root / "vault")
                tools = ToolRegistry(memory)
                agent = Agent(SessionStore(root / "sessions"), memory, tools, FakeLLM())
                result = agent.turn(None, "/find roadmap")
            finally:
                if old is None:
                    os.environ.pop("SANKALP_ALLOWED_ROOTS", None)
                else:
                    os.environ["SANKALP_ALLOWED_ROOTS"] = old

            self.assertEqual(result["tool_calls"][0]["name"], "file_find")
            self.assertIn("roadmap.md", result["message"]["content"])

    def test_natural_file_find_uses_target_and_container_path(self):
        class PlannerLLM(FakeLLM):
            def agent_next_action(self, message, tools, observations, options=None):
                if not observations:
                    return {
                        "action": "tool",
                        "tool": "file_find",
                        "arguments": {"query": "health", "path": "~/Desktop/Personal", "kind": "directory"},
                    }
                return {"action": "answer", "answer": "Found `/personal/health`."}

        with tempfile.TemporaryDirectory() as tmp:
            old_roots = os.environ.get("SANKALP_ALLOWED_ROOTS")
            old_home = os.environ.get("HOME")
            home = Path(tmp) / "home"
            desktop = home / "Desktop"
            personal = desktop / "Personal"
            (personal / "health").mkdir(parents=True)
            (personal / "health" / "test_report.pdf").write_text("pdf", encoding="utf-8")
            os.environ["HOME"] = str(home)
            os.environ["SANKALP_ALLOWED_ROOTS"] = str(desktop)
            try:
                memory = ObsidianMemory(Path(tmp) / "vault")
                tools = ToolRegistry(memory)
                agent = Agent(SessionStore(Path(tmp) / "sessions"), memory, tools, PlannerLLM())
                result = agent.turn(None, "can you recursively check my personal folder under desktop and find any health folder under that?")
            finally:
                if old_roots is None:
                    os.environ.pop("SANKALP_ALLOWED_ROOTS", None)
                else:
                    os.environ["SANKALP_ALLOWED_ROOTS"] = old_roots
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual(result["tool_calls"][0]["name"], "file_find")
            self.assertEqual(result["tool_calls"][0]["input"]["query"], "health")
            self.assertEqual(result["tool_calls"][0]["input"]["kind"], "directory")
            self.assertIn("/personal/health", result["message"]["content"].lower())

    def test_agentic_loop_can_refine_insurance_document_search(self):
        class PlannerLLM(FakeLLM):
            def agent_next_action(self, message, tools, observations, options=None):
                if not observations:
                    return {"action": "tool", "tool": "file_find", "arguments": {"query": "insurance", "path": "~/Desktop", "kind": "any"}}
                if len(observations) == 1:
                    matches = observations[0]["output"]["matches"]
                    folder = next(item["path"] for item in matches if item["path"].endswith("insurance_dad_mom"))
                    return {"action": "tool", "tool": "file_list", "arguments": {"path": folder}}
                return {
                    "action": "answer",
                    "answer": "Found insurance docs in `Desktop/Personal/health/insurance_dad_mom`, including `care_supreme_1Cr_both.jpeg`.",
                }

        with tempfile.TemporaryDirectory() as tmp:
            old_roots = os.environ.get("SANKALP_ALLOWED_ROOTS")
            old_home = os.environ.get("HOME")
            home = Path(tmp) / "home"
            insurance = home / "Desktop" / "Personal" / "health" / "insurance_dad_mom"
            insurance.mkdir(parents=True)
            (insurance / "care_supreme_1Cr_both.jpeg").write_text("image", encoding="utf-8")
            vehicle = home / "Desktop" / "Personal" / "Documents" / "Vehicle"
            vehicle.mkdir(parents=True)
            (vehicle / "Himalayan_Insurance_24-25.pdf").write_text("pdf", encoding="utf-8")
            os.environ["HOME"] = str(home)
            os.environ["SANKALP_ALLOWED_ROOTS"] = str(home / "Desktop")
            try:
                memory = ObsidianMemory(Path(tmp) / "vault")
                tools = ToolRegistry(memory)
                agent = Agent(SessionStore(Path(tmp) / "sessions"), memory, tools, PlannerLLM())
                result = agent.turn(None, "can you find some insurance related documents under some folder in my Desktop?")
            finally:
                if old_roots is None:
                    os.environ.pop("SANKALP_ALLOWED_ROOTS", None)
                else:
                    os.environ["SANKALP_ALLOWED_ROOTS"] = old_roots
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual([call["name"] for call in result["tool_calls"]], ["file_find", "file_list"])
            self.assertIn("insurance_dad_mom", result["message"]["content"])
            self.assertIn("care_supreme_1Cr_both.jpeg", result["message"]["content"])

    def test_agentic_followup_can_inspect_previous_folder(self):
        class PlannerLLM(FakeLLM):
            def agent_next_action(self, message, tools, observations, options=None):
                if "what is in it" in message.lower() and not observations:
                    if "insurance_dad_mom" not in message:
                        raise AssertionError("previous folder path was not included in agent context")
                    return {
                        "action": "tool",
                        "tool": "file_list",
                        "arguments": {"path": "~/Desktop/Personal/health/insurance_dad_mom"},
                    }
                if observations:
                    return {
                        "action": "answer",
                        "answer": "It contains `care_supreme_1Cr_both.jpeg` and `hdfc_optima_secure_50L_both.jpeg`.",
                    }
                return {
                    "action": "answer",
                    "answer": "Found `/Users/test/Desktop/Personal/health/insurance_dad_mom`.",
                }

        with tempfile.TemporaryDirectory() as tmp:
            old_roots = os.environ.get("SANKALP_ALLOWED_ROOTS")
            old_home = os.environ.get("HOME")
            home = Path(tmp) / "home"
            folder = home / "Desktop" / "Personal" / "health" / "insurance_dad_mom"
            folder.mkdir(parents=True)
            (folder / "care_supreme_1Cr_both.jpeg").write_text("image", encoding="utf-8")
            (folder / "hdfc_optima_secure_50L_both.jpeg").write_text("image", encoding="utf-8")
            os.environ["HOME"] = str(home)
            os.environ["SANKALP_ALLOWED_ROOTS"] = str(home / "Desktop")
            try:
                memory = ObsidianMemory(Path(tmp) / "vault")
                tools = ToolRegistry(memory)
                store = SessionStore(Path(tmp) / "sessions")
                agent = Agent(store, memory, tools, PlannerLLM())
                session = store.create()
                session.messages.append({
                    "role": "assistant",
                    "content": "Found `/Users/test/Desktop/Personal/health/insurance_dad_mom`.",
                })
                store.save(session)
                result = agent.turn(session.session_id, "what is in it?")
            finally:
                if old_roots is None:
                    os.environ.pop("SANKALP_ALLOWED_ROOTS", None)
                else:
                    os.environ["SANKALP_ALLOWED_ROOTS"] = old_roots
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual(result["tool_calls"][-1]["name"], "file_list")
            self.assertIn("care_supreme_1Cr_both.jpeg", result["message"]["content"])

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
