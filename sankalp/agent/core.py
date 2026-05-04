from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sankalp.agent.llm import LLMAdapter
from sankalp.memory import ObsidianMemory
from sankalp.sessions import Session, SessionStore
from sankalp.tools import ToolRegistry


class Agent:
    def __init__(self, sessions: SessionStore, memory: ObsidianMemory, tools: ToolRegistry, llm: LLMAdapter | None = None):
        self.sessions = sessions
        self.memory = memory
        self.tools = tools
        self.llm = llm or LLMAdapter()

    def turn(self, session_id: str | None, content: str) -> dict[str, Any]:
        session = self.sessions.get(session_id)
        content = content.strip()
        session.messages.append({"role": "user", "content": content})
        self.memory.append_session_turn(session.session_id, "user", content)

        routed = self._route_explicit_tool(session, content)
        if routed is not None:
            answer = routed
        else:
            hits = self.memory.retrieve(content)
            memory_context = "\n\n".join(f"[{hit.path}]\n{hit.snippet}" for hit in hits)
            try:
                result = self.llm.complete(session.messages, memory_context, session.previous_response_id)
                session.previous_response_id = result.get("response_id")
                answer = result["text"]
            except Exception as exc:
                answer = f"I hit an LLM adapter error: {exc}"

        session.messages.append({"role": "assistant", "content": answer})
        self.memory.append_session_turn(session.session_id, "assistant", answer)
        self.sessions.save(session)
        return self._payload(session, answer)

    def _route_explicit_tool(self, session: Session, content: str) -> str | None:
        lowered = content.lower()
        if lowered.startswith("remember:") or lowered.startswith("remember "):
            text = content.split(":", 1)[1].strip() if ":" in content else content[len("remember "):].strip()
            result = self.tools.call("memory_remember", text=text, source=f"session:{session.session_id}")
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                return "Remembered. I appended it to the Obsidian inbox."
            return f"I could not save that memory: {result.output}"

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

    def _payload(self, session: Session, answer: str) -> dict[str, Any]:
        return {
            "session": session.compact(),
            "message": {"role": "assistant", "content": answer},
            "messages": session.messages,
            "tool_calls": session.tool_calls,
            "memory": self.memory.list_recent(limit=12),
        }
