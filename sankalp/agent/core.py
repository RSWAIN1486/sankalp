from __future__ import annotations

import re
import time
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

    def turn(self, session_id: str | None, content: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        request = request or {}
        attachments = list(request.get("attachments") or [])
        options = dict(request.get("options") or {})
        session = self.sessions.get(session_id)
        content = content.strip()
        stored_content = self._stored_user_content(content, attachments)
        session.messages.append({"role": "user", "content": stored_content})
        self.memory.append_session_turn(session.session_id, "user", stored_content)

        routed = self._route_explicit_tool(session, content)
        if routed is not None:
            answer = routed
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

    def _stored_user_content(self, content: str, attachments: list[dict[str, Any]]) -> str:
        if not attachments:
            return content
        names = ", ".join(str(item.get("name") or "attachment") for item in attachments)
        base = content or "(attached files)"
        return f"{base}\n\nAttached: {names}"

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
