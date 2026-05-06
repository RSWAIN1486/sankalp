from __future__ import annotations

import re
import threading
import time
from dataclasses import asdict
from typing import Any

from sankalp.agent.llm import LLMAdapter
from sankalp.memory import ObsidianMemory
from sankalp.sessions import Session, SessionStore
from sankalp.sessions.store import title_from_query
from sankalp.tools import ToolRegistry


class Agent:
    def __init__(self, sessions: SessionStore, memory: ObsidianMemory, tools: ToolRegistry, llm: LLMAdapter | None = None):
        self.sessions = sessions
        self.memory = memory
        self.tools = tools
        self.llm = llm or LLMAdapter()

    def turn(self, session_id: str | None, content: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        request = request or {}
        attachments = list(request.get("attachments") or [])
        options = dict(request.get("options") or {})
        session = self.sessions.get(session_id)
        edit_index = request.get("edit_index")
        if isinstance(edit_index, int) and 0 <= edit_index < len(session.messages):
            session.messages = session.messages[:edit_index]
            session.tool_calls = []
            session.previous_response_id = None
        should_title = not session.messages and session.title_source != "manual"
        content = content.strip()
        stored_content = self._stored_user_content(content, attachments)
        session.messages.append({"role": "user", "content": stored_content})
        self.memory.append_session_turn(session.session_id, "user", stored_content)
        if should_title:
            session.title = title_from_query(content)
            session.title_source = "fallback"

        routed = self._route_explicit_tool(session, content, options)
        if routed is not None:
            answer = routed
        else:
            selected = self._route_llm_selected_tool(session, content, options)
            if selected is not None:
                answer = selected
            else:
                hits = self.memory.retrieve(content)
                memory_context = self._memory_context(content, hits)
                try:
                    result = self.llm.complete(session.messages, memory_context, session.previous_response_id, options, attachments)
                    session.previous_response_id = result.get("response_id")
                    answer = result["text"]
                except Exception as exc:
                    answer = f"I hit an LLM adapter error: {exc}"
                self._maybe_infer_profile_trait(session, content)

        session.messages.append({"role": "assistant", "content": answer})
        self.memory.append_session_turn(session.session_id, "assistant", answer)
        self.sessions.save(session)
        if should_title:
            self._generate_title_async(session.session_id, content, options)
        return self._payload(session, answer)

    def turn_stream(self, session_id: str | None, content: str, request: dict[str, Any] | None = None):
        request = request or {}
        attachments = list(request.get("attachments") or [])
        options = dict(request.get("options") or {})
        session = self.sessions.get(session_id)
        edit_index = request.get("edit_index")
        if isinstance(edit_index, int) and 0 <= edit_index < len(session.messages):
            session.messages = session.messages[:edit_index]
            session.tool_calls = []
            session.previous_response_id = None
        should_title = not session.messages and session.title_source != "manual"
        content = content.strip()
        stored_content = self._stored_user_content(content, attachments)
        session.messages.append({"role": "user", "content": stored_content})
        self.memory.append_session_turn(session.session_id, "user", stored_content)
        if should_title:
            session.title = title_from_query(content)
            session.title_source = "fallback"
        yield {"event": "status", "data": {"label": "Thinking", "detail": "Preparing context"}}

        routed = self._route_explicit_tool(session, content, options)
        answer = ""
        if routed is not None:
            answer = routed
            yield {"event": "status", "data": {"label": "Done", "detail": "Handled by built-in tool"}}
            yield {"event": "delta", "data": {"text": answer}}
        else:
            selected = self._route_llm_selected_tool(session, content, options)
            if selected is not None:
                answer = selected
                yield {"event": "status", "data": {"label": "Done", "detail": "Handled by selected tool"}}
                yield {"event": "delta", "data": {"text": answer}}
            else:
                hits = self.memory.retrieve(content)
                memory_context = self._memory_context(content, hits)
                yield {"event": "status", "data": {"label": "Thinking", "detail": "Generating response"}}
                try:
                    streamer = getattr(self.llm, "stream_complete", None)
                    if callable(streamer):
                        for event in streamer(session.messages, memory_context, session.previous_response_id, options, attachments):
                            kind = event.get("type")
                            if kind == "delta":
                                text = str(event.get("text") or "")
                                if text:
                                    answer += text
                                    yield {"event": "delta", "data": {"text": text}}
                            elif kind == "reasoning":
                                text = str(event.get("text") or "")
                                if text:
                                    yield {"event": "reasoning", "data": {"text": text}}
                            elif kind == "response_id":
                                session.previous_response_id = event.get("response_id")
                    else:
                        result = self.llm.complete(session.messages, memory_context, session.previous_response_id, options, attachments)
                        session.previous_response_id = result.get("response_id")
                        answer = str(result.get("text") or "")
                        if answer:
                            yield {"event": "delta", "data": {"text": answer}}
                except Exception as exc:
                    answer = f"I hit an LLM adapter error: {exc}"
                    yield {"event": "delta", "data": {"text": answer}}
                self._maybe_infer_profile_trait(session, content)

        session.messages.append({"role": "assistant", "content": answer})
        self.memory.append_session_turn(session.session_id, "assistant", answer)
        self.sessions.save(session)
        if should_title:
            self._generate_title_async(session.session_id, content, options)
        payload = self._payload(session, answer)
        yield {"event": "session", "data": {"session": payload["session"], "tool_calls": payload.get("tool_calls", [])}}
        yield {"event": "done", "data": payload}

    def _route_explicit_tool(self, session: Session, content: str, options: dict[str, Any]) -> str | None:
        lowered = content.lower()
        if lowered.startswith("/remember ") or lowered.startswith("remember:") or lowered.startswith("remember "):
            if lowered.startswith("/remember "):
                text = content[len("/remember "):].strip()
            elif ":" in content:
                text = content.split(":", 1)[1].strip()
            else:
                text = content[len("remember "):].strip()
            result = self.tools.call("memory_remember", text=text, source=f"session:{session.session_id}")
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                return "Remembered. I appended it to the Obsidian inbox."
            return f"I could not save that memory: {result.output}"

        if self._is_memory_lookup_request(lowered):
            search_query = self._memory_search_query(content, options)
            result = self.tools.call("memory_search", query=search_query, original_query=content, limit=6)
            session.tool_calls.append(asdict(result))
            if result.status != "ok":
                return f"I could not search memory: {result.output}"
            return self._answer_memory_search(session, content, result.output, options)

        if lowered.startswith("/fetch "):
            url = content[len("/fetch "):].strip()
            result = self.tools.call("browser_fetch", url=url)
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                text = result.output.get("text", "")
                return f"Fetched `{url}`.\n\n{text[:2500]}"
            return f"Fetch failed: {result.output}"

        if lowered.startswith("/read "):
            path = content[len("/read "):].strip()
            result = self.tools.call("file_read", path=path)
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                return f"Read `{result.output['path']}`.\n\n{result.output['text']}"
            return f"Read failed: {result.output}"

        if lowered.startswith("/append "):
            body = content[len("/append "):]
            if "::" not in body:
                return "Use `/append path :: text`."
            path, text = body.split("::", 1)
            result = self.tools.call("file_append", path=path.strip(), text=text)
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                return f"Appended to `{result.output['path']}`."
            return f"Append failed: {result.output}"

        if lowered.startswith("/sh "):
            command = content[len("/sh "):].strip()
            result = self.tools.call("terminal", command=command)
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                out = result.output.get("stdout") or result.output.get("stderr") or "(no output)"
                return f"Command finished with code {result.output['returncode']}.\n\n{out}"
            return f"Command blocked or failed: {result.output}"

        return None

    def _route_llm_selected_tool(self, session: Session, content: str, options: dict[str, Any]) -> str | None:
        if not hasattr(self.llm, "select_tool"):
            return None
        selection = self.llm.select_tool(content, self._llm_selectable_tools(), options)
        if not selection:
            return None
        tool = selection.get("tool")
        arguments = dict(selection.get("arguments") or {})
        if tool == "memory_search":
            selected_query = str(arguments.get("query") or content)
            search_query = self._memory_search_query(selected_query, options)
            result = self.tools.call("memory_search", query=search_query, original_query=content, limit=6)
            session.tool_calls.append(asdict(result))
            if result.status != "ok":
                return f"I could not search memory: {result.output}"
            return self._answer_memory_search(session, content, result.output, options)
        if tool == "browser_fetch":
            url = str(arguments.get("url") or "").strip()
            if not url:
                return None
            result = self.tools.call("browser_fetch", url=url)
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                text = result.output.get("text", "")
                return f"Fetched `{url}`.\n\n{text[:2500]}"
            return f"Fetch failed: {result.output}"
        if tool == "file_read":
            path = str(arguments.get("path") or "").strip()
            if not path:
                return None
            result = self.tools.call("file_read", path=path)
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                return f"Read `{result.output['path']}`.\n\n{result.output['text']}"
            return f"Read failed: {result.output}"
        return None

    def _llm_selectable_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "memory_search",
                "description": "Search the configured Obsidian memory vault or workspace for notes relevant to the user request.",
                "arguments": {"query": "search terms to use"},
            },
            {
                "name": "browser_fetch",
                "description": "Fetch and extract readable text from a specific http or https URL the user wants read.",
                "arguments": {"url": "http or https URL"},
            },
            {
                "name": "file_read",
                "description": "Read a local file path when the user asks to inspect that file.",
                "arguments": {"path": "path inside an allowed root"},
            },
        ]

    def _memory_search_query(self, content: str, options: dict[str, Any]) -> str:
        if hasattr(self.llm, "memory_search_query"):
            query = self.llm.memory_search_query(content, options)
            if query:
                return query
        return content

    def _is_memory_lookup_request(self, lowered: str) -> bool:
        if any(phrase in lowered for phrase in ["in my memory", "from my memory", "from memory", "search memory", "check memory"]):
            return True
        if re.search(r"\b(check|search|look for|find|retrieve)\s+(my|the|your)\s+memory\b", lowered):
            return True
        return bool(re.search(r"\b(do you see|find|retrieve|look for|search)\b.*\b(notes?|documentation|docs?|memory)\b", lowered))

    def _format_memory_search(self, query: str, output: dict[str, Any]) -> str:
        status = output.get("status") or {}
        hits = output.get("hits") or []
        workspace = status.get("workspace") or "whole vault"
        if not hits:
            return (
                "I searched your configured Obsidian memory and did not find matching notes.\n\n"
                f"Vault: `{status.get('vault', 'unknown')}`\n"
                f"Search scope: whole vault, excluding `Sessions/`\n"
                f"Configured workspace: `{workspace}`"
            )
        lines = [
            "I searched your configured Obsidian memory and found:",
            "",
        ]
        for hit in hits:
            lines.append(f"- `{hit['path']}`: {hit['snippet']}")
        lines.extend([
            "",
            f"Vault: `{status.get('vault', 'unknown')}`",
            f"Search scope: whole vault, excluding `Sessions/`",
            f"Configured workspace: `{workspace}`",
        ])
        return "\n".join(lines)

    def _answer_memory_search(self, session: Session, content: str, output: dict[str, Any], options: dict[str, Any]) -> str:
        hits = output.get("hits") or []
        if not hits:
            return self._format_memory_search(content, output)
        mode = self._memory_lookup_mode(content)
        if mode == "confirm":
            return self._format_memory_confirmation(output)
        memory_context = "\n\n".join(f"[{hit['path']}]\n{hit.get('text') or hit['snippet']}" for hit in hits)
        prompt = (
            "Answer the user's memory lookup using only these Obsidian notes.\n"
            "Response policy:\n"
            "- If the user is only checking whether relevant notes exist, say yes or no, name the most relevant source paths, and ask what they want to inspect next.\n"
            "- If the user asks for specific information, answer that specific question from the notes and cite the source paths.\n"
            "- If the notes do not contain enough information to answer, say what was found and what is missing.\n"
            "- Do not summarize everything unless the user asks for a summary.\n\n"
            f"User request: {content}"
        )
        try:
            answer_options = dict(options)
            answer_options["response_mode"] = "grounded_memory_answer"
            result = self.llm.complete(
                [{"role": "user", "content": prompt}],
                memory_context,
                None,
                answer_options,
                [],
            )
            text = str(result.get("text") or "").strip()
            if text and result.get("provider") != "local-fallback":
                return text
        except Exception:
            pass
        return self._format_memory_search(content, output)

    def _format_memory_confirmation(self, output: dict[str, Any]) -> str:
        status = output.get("status") or {}
        hits = output.get("hits") or []
        workspace = status.get("workspace") or "whole vault"
        paths = "\n".join(f"- `{hit['path']}`" for hit in hits[:5])
        return (
            "Yes, I found relevant notes in your Obsidian memory.\n\n"
            f"{paths}\n\n"
            f"Search scope: whole vault, excluding `Sessions/`\n"
            f"Configured workspace: `{workspace}`\n\n"
            "What would you like to know from these notes?"
        )

    def _memory_lookup_mode(self, content: str) -> str:
        words = re.findall(r"[A-Za-z0-9_']+", content.lower())
        question_words = {"what", "which", "who", "where", "when", "why", "how"}
        detail_verbs = {"explain", "summarize", "compare", "list", "describe", "tell", "show"}
        if any(word in question_words or word in detail_verbs for word in words):
            return "answer"
        if "?" in content and len(words) > 8:
            return "answer"
        return "confirm"

    def _stored_user_content(self, content: str, attachments: list[dict[str, Any]]) -> str:
        if not attachments:
            return content
        names = ", ".join(str(item.get("name") or "attachment") for item in attachments)
        base = content or "(attached files)"
        return f"{base}\n\nAttached: {names}"

    def _generate_title_async(self, session_id: str, content: str, options: dict[str, Any]) -> None:
        def worker() -> None:
            try:
                title = self.llm.title_for_query(content, options)
                self.sessions.update_generated_title(session_id, title)
            except Exception:
                return

        threading.Thread(target=worker, daemon=True).start()

    def _memory_context(self, query: str, hits: list[Any]) -> str:
        profile = self.memory.read_profile()
        chunks = []
        if profile["self_profile"]:
            chunks.append("[People/you.md: user-authored profile]\n" + profile["self_profile"])
        if profile["traits"]:
            trait_text = "\n".join(f"- {item['text']}" for item in profile["traits"])
            chunks.append("[People/you.md: agent-inferred traits]\n" + trait_text)
        chunks.extend(f"[{hit.path}]\n{hit.snippet}" for hit in hits)
        return "\n\n".join(chunks)

    def _maybe_infer_profile_trait(self, session: Session, content: str) -> None:
        if len(self.memory.read_profile()["traits"]) >= 20:
            return
        patterns = [
            (r"\bI prefer ([^.?!\n]{4,120})", "The user prefers {value}."),
            (r"\bI like ([^.?!\n]{4,120})", "The user likes {value}."),
            (r"\bI usually ([^.?!\n]{4,120})", "The user usually {value}."),
            (r"\bI care about ([^.?!\n]{4,120})", "The user cares about {value}."),
            (r"\bI want ([^.?!\n]{4,120})", "The user wants {value}."),
            (r"\bI don't like ([^.?!\n]{4,120})", "The user dislikes {value}."),
            (r"\bI am ([^.?!\n]{4,120})", "The user describes themself as {value}."),
        ]
        for pattern, template in patterns:
            match = re.search(pattern, content, flags=re.I)
            if not match:
                continue
            value = match.group(1).strip()
            trait = template.format(value=value)
            trait_id = self.memory.add_inferred_trait(trait, evidence=f"session:{session.session_id}")
            if trait_id:
                session.tool_calls.append({
                    "name": "profile_infer",
                    "status": "ok",
                    "input": {"message": content[:240]},
                    "output": {"trait_id": trait_id, "trait": trait},
                    "started_at": time.time(),
                    "finished_at": time.time(),
                })
            return

    def _payload(self, session: Session, answer: str) -> dict[str, Any]:
        return {
            "session": session.compact(),
            "message": {"role": "assistant", "content": answer},
            "messages": session.messages,
            "tool_calls": session.tool_calls,
            "memory": self.memory.list_recent(limit=12),
            "memory_status": self.memory.status(),
        }
