from __future__ import annotations

import json
import re
import shlex
import threading
import time
from dataclasses import asdict
from typing import Any

from sankalp.agent.llm import LLMAdapter
from sankalp.computer import ComputerTaskRunner
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

        auto_save_after_answer = self._should_auto_save_after_answer(content)
        routed = None if auto_save_after_answer else self._route_explicit_tool(session, content, options)
        if routed is not None:
            answer = routed
        else:
            selected = self._run_web_research(session, content, options) if self._is_web_research_request(content.lower()) else self._run_agentic_tool_loop(session, content, options)
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
            if auto_save_after_answer and answer and not answer.startswith("I hit an LLM adapter error:"):
                save_result = self._save_answer_to_memory(session, content, answer, options)
                if save_result:
                    answer = f"{answer}\n\n{save_result}"

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

        auto_save_after_answer = self._should_auto_save_after_answer(content)
        routed = None if auto_save_after_answer else self._route_explicit_tool(session, content, options)
        answer = ""
        if routed is not None:
            answer = routed
            yield {"event": "status", "data": {"label": "Done", "detail": "Handled by built-in tool"}}
            yield {"event": "delta", "data": {"text": answer}}
        else:
            selected = self._run_web_research(session, content, options) if self._is_web_research_request(content.lower()) else self._run_agentic_tool_loop(session, content, options)
            if selected is not None:
                answer = selected
                if auto_save_after_answer and answer and not answer.startswith("I hit an LLM adapter error:"):
                    save_result = self._save_answer_to_memory(session, content, answer, options)
                    if save_result:
                        answer += f"\n\n{save_result}"
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
                if auto_save_after_answer and answer and not answer.startswith("I hit an LLM adapter error:"):
                    save_result = self._save_answer_to_memory(session, content, answer, options)
                    if save_result:
                        answer += f"\n\n{save_result}"
                        yield {"event": "delta", "data": {"text": f"\n\n{save_result}"}}

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
            target = self._memory_save_target(content, text, options)
            result = self.tools.call(
                "memory_remember",
                text=text,
                source=f"session:{session.session_id}",
                folder=target.get("folder"),
                note=target.get("note"),
            )
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                target_path = result.output.get("target", {}).get("path") or result.output.get("path")
                return f"Remembered. I saved it to `{target_path}`."
            return f"I could not save that memory: {result.output}"

        if self._is_obsidian_save_request(lowered):
            text = self._memory_capture_text_for_request(session, content)
            if not text:
                return "I couldn't find prior content to save. Share the content or use `/remember <text>`."
            target = self._memory_save_target(content, text, options)
            result = self.tools.call(
                "memory_remember",
                text=text,
                source=f"session:{session.session_id}",
                folder=target.get("folder"),
                note=target.get("note"),
            )
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                target_path = result.output.get("target", {}).get("path") or result.output.get("path")
                return f"Saved to Obsidian at `{target_path}`."
            return f"I could not save that to Obsidian: {result.output}"

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

        if lowered.startswith("/research "):
            query = content[len("/research "):].strip()
            return self._run_web_research(session, query, options)

        if lowered == "/computer" or lowered.startswith("/computer "):
            return self._route_computer_command(session, content, options)

        if lowered.startswith("/read "):
            path = content[len("/read "):].strip()
            result = self.tools.call("file_read", path=path)
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                return f"Read `{result.output['path']}`.\n\n{result.output['text']}"
            return f"Read failed: {result.output}"

        if lowered in {"/ls", "/files", "/folders"} or lowered.startswith(("/ls ", "/files ", "/folders ")):
            path = content.split(maxsplit=1)[1].strip() if len(content.split(maxsplit=1)) > 1 else "."
            return self._route_file_list(session, path)

        if lowered.startswith(("/find ", "/find-file ", "/find-folder ")):
            query = content.split(maxsplit=1)[1].strip() if len(content.split(maxsplit=1)) > 1 else ""
            kind = "directory" if lowered.startswith("/find-folder ") else "file" if lowered.startswith("/find-file ") else "any"
            return self._route_file_find(session, query, kind=kind)

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

    def _route_computer_command(self, session: Session, content: str, options: dict[str, Any]) -> str:
        body = content[len("/computer"):].strip()
        if not body or body in {"status", "help"}:
            result = self.tools.call("computer_status")
            session.tool_calls.append(asdict(result))
            if body == "help":
                return self._computer_help(result.output)
            return self._format_computer_status(result.output)

        lowered = body.lower()
        if lowered in {"apps", "list", "list apps"}:
            result = self.tools.call("computer_list_apps")
            session.tool_calls.append(asdict(result))
            return self._format_computer_apps(result)

        if lowered.startswith("permissions"):
            parts = self._split_computer_args(body)
            target = parts[1] if len(parts) > 1 else "accessibility"
            result = self.tools.call("computer_open_permissions", target=target)
            session.tool_calls.append(asdict(result))
            return self._format_computer_action(result, success=f"Opened macOS `{target}` permission settings.")

        if lowered.startswith("task "):
            instruction = body[len("task "):].strip()
            if not instruction:
                return "Use `/computer task <what you want done>`."
            runner = ComputerTaskRunner(self.tools, self.llm)
            answer, results = runner.run(instruction, options)
            session.tool_calls.extend(asdict(item) for item in results)
            return answer

        if lowered.startswith("open "):
            app = body[len("open "):].strip()
            result = self.tools.call("computer_open_app", app=app)
            session.tool_calls.append(asdict(result))
            return self._format_computer_action(result, success=f"Opened `{app}`.")

        if lowered.startswith("inspect "):
            app = body[len("inspect "):].strip()
            result = self.tools.call("computer_inspect", app=app, max_depth=3, max_children=60)
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                return f"Inspected `{app}`.\n\n```plaintext\n{result.output.get('tree', '').strip()}\n```"
            return f"Inspect failed: {result.output}"

        if lowered == "screenshot":
            result = self.tools.call("computer_screenshot")
            session.tool_calls.append(asdict(result))
            if result.status == "ok":
                return f"Captured screenshot at `{result.output.get('path')}`."
            return f"Screenshot failed: {result.output}"

        if lowered.startswith("click "):
            return self._route_computer_click(session, body[len("click "):].strip())

        if lowered.startswith("type "):
            return self._route_computer_type(session, body[len("type "):], mode="type")

        if lowered.startswith("set "):
            return self._route_computer_type(session, body[len("set "):], mode="set")

        if lowered.startswith("key "):
            parts = self._split_computer_args(body[len("key "):].strip())
            if len(parts) < 2:
                return "Use `/computer key <app> <key>`."
            app, key = parts[0], parts[1]
            result = self.tools.call("computer_press_key", app=app, key=key)
            session.tool_calls.append(asdict(result))
            return self._format_computer_action(result, success=f"Pressed `{key}` in `{app}`.")

        if lowered.startswith("scroll "):
            parts = self._split_computer_args(body[len("scroll "):].strip())
            if len(parts) < 2:
                return "Use `/computer scroll <app> <down|up|left|right> [pages]`."
            pages = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            result = self.tools.call("computer_scroll", app=parts[0], direction=parts[1], pages=pages)
            session.tool_calls.append(asdict(result))
            return self._format_computer_action(result, success=f"Scrolled `{parts[1]}` in `{parts[0]}`.")

        return self._computer_help({})

    def _route_computer_click(self, session: Session, body: str) -> str:
        parts = self._split_computer_args(body)
        if len(parts) < 2:
            return "Use `/computer click <app> <element_path>` or `/computer click screen <x>,<y>`."
        app, target = parts[0], parts[1]
        coords = self._parse_computer_coords(target)
        if app.lower() == "screen" and coords:
            result = self.tools.call("computer_click", x=coords[0], y=coords[1])
        elif coords:
            result = self.tools.call("computer_click", app=app, x=coords[0], y=coords[1])
        else:
            result = self.tools.call("computer_click", app=app, element_path=target)
        session.tool_calls.append(asdict(result))
        return self._format_computer_action(result, success=f"Clicked `{target}`.")

    def _route_computer_type(self, session: Session, body: str, mode: str) -> str:
        if "::" not in body:
            return f"Use `/computer {mode} <app> <element_path> :: <text>`."
        left, text = body.split("::", 1)
        parts = self._split_computer_args(left.strip())
        if len(parts) < 1:
            return f"Use `/computer {mode} <app> [element_path] :: <text>`."
        app = parts[0]
        element_path = parts[1] if len(parts) > 1 else ""
        tool = "computer_type_text" if mode == "type" else "computer_set_value"
        result = self.tools.call(tool, app=app, element_path=element_path, text=text.strip()) if mode == "type" else self.tools.call(
            tool,
            app=app,
            element_path=element_path,
            value=text.strip(),
        )
        session.tool_calls.append(asdict(result))
        action = "Typed into" if mode == "type" else "Set"
        return self._format_computer_action(result, success=f"{action} `{element_path}` in `{app}`.")

    def _split_computer_args(self, value: str) -> list[str]:
        try:
            return shlex.split(value)
        except ValueError:
            return value.split()

    def _parse_computer_coords(self, target: str) -> tuple[int, int] | None:
        match = re.fullmatch(r"\s*(\d+)\s*,\s*(\d+)\s*", target)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    def _format_computer_status(self, output: dict[str, Any]) -> str:
        available = "available" if output.get("available") else "not available"
        permissions = output.get("permissions") or {}
        return (
            f"Computer Use is `{available}` with `{output.get('backend', 'unknown')}`.\n\n"
            f"- macOS: `{output.get('is_macos')}`\n"
            f"- osascript: `{(output.get('tools') or {}).get('osascript', '')}`\n"
            f"- screencapture: `{(output.get('tools') or {}).get('screencapture', '')}`\n"
            f"- Accessibility: {permissions.get('accessibility', 'unknown')}\n"
            f"- Screen Recording: {permissions.get('screen_recording', 'unknown')}\n"
            f"- Dev mode permission target: {permissions.get('dev_mode_grant_to', 'launching terminal')}\n"
            f"- Installed app permission target: {permissions.get('installed_app_grant_to', 'Sankalp.app')}"
        )

    def _format_computer_apps(self, result: Any) -> str:
        if result.status != "ok":
            return f"Could not list controllable apps: {result.output}"
        apps = result.output.get("apps") or []
        if not apps:
            return "No visible apps were reported."
        return "Computer Use can currently see these apps:\n\n" + "\n".join(f"- {app}" for app in apps)

    def _format_computer_action(self, result: Any, success: str) -> str:
        if result.status == "ok":
            return success
        return f"Computer action failed: {result.output}"

    def _computer_help(self, status: dict[str, Any]) -> str:
        prefix = ""
        if status:
            prefix = self._format_computer_status(status) + "\n\n"
        return prefix + (
            "Computer Use commands:\n\n"
            "- `/computer apps`\n"
            "- `/computer permissions [accessibility|screen]`\n"
            "- `/computer open <app>`\n"
            "- `/computer inspect <app>`\n"
            "- `/computer screenshot`\n"
            "- `/computer click <app> <element_path>` or `/computer click screen <x>,<y>`\n"
            "- `/computer type <app> [element_path] :: <text>`\n"
            "- `/computer set <app> <element_path> :: <text>`\n"
            "- `/computer key <app> <Return|Tab|Escape|Command-L>`\n"
            "- `/computer scroll <app> <down|up|left|right> [pages]`\n"
            "- `/computer task <low-risk instruction>`"
            "\n\nIn dev mode, grant macOS permissions to the app that launched the dev server, usually Terminal or iTerm. "
            "Sankalp.app appears in Privacy settings only when you run the installed app bundle."
        )

    def _is_obsidian_save_request(self, lowered: str) -> bool:
        explicit_save_verbs = ["save", "document", "remember", "store", "write down"]
        if any(word in lowered for word in ["obsidian", "vault"]) and any(word in lowered for word in explicit_save_verbs):
            return True
        shorthand_patterns = [
            r"^\s*(save|document|store)\s+(it|this|that|them)\b",
            r"\b(can you|please)\s+(save|document|store)\s+(it|this|that|them)\b",
            r"\b(save|document|store)\s+(this|that|it|them)\s*(for me)?\s*$",
        ]
        return any(re.search(pattern, lowered) for pattern in shorthand_patterns)

    def _memory_capture_text_for_request(self, session: Session, content: str) -> str:
        lowered = content.lower()
        if any(word in lowered for word in ["above", "that", "those", "them", "it"]):
            for item in reversed(session.messages[:-1]):
                if item.get("role") == "assistant":
                    previous = str(item.get("content") or "").strip()
                    if previous:
                        return previous
        return content.strip()

    def _should_auto_save_after_answer(self, content: str) -> bool:
        lowered = content.lower()
        wants_save = self._is_obsidian_save_request(lowered)
        research_like = any(term in lowered for term in [
            "find", "explore", "research", "latest", "paper", "papers", "look up", "search",
        ])
        return wants_save and research_like

    def _is_web_research_request(self, lowered: str) -> bool:
        if lowered.startswith(("/research ", "/fetch ", "/read ", "/remember ", "/append ", "/sh ")):
            return False
        if "memory" in lowered or "obsidian" in lowered and not any(term in lowered for term in ["find", "research", "latest", "papers"]):
            return False
        return bool(
            re.search(r"\b(find|research|look up|search)\b.*\b(latest|web|online|papers?|sources?|news|details?)\b", lowered)
            or re.search(r"\b(latest|recent)\b.*\b(papers?|news|sources?|research)\b", lowered)
        )

    def _run_web_research(self, session: Session, query: str, options: dict[str, Any]) -> str:
        result = self.tools.call("browser_search", query=query, limit=6, include_content=True)
        session.tool_calls.append(asdict(result))
        if result.status != "ok":
            return f"Research failed: {result.output}"
        return self._answer_web_research(query, result.output, options)

    def _save_answer_to_memory(self, session: Session, request_text: str, answer_text: str, options: dict[str, Any]) -> str | None:
        note_text = self._memory_note_content_for_save(answer_text)
        target = self._memory_save_target(request_text, note_text, options)
        result = self.tools.call(
            "memory_remember",
            text=note_text,
            source=f"session:{session.session_id}",
            folder=target.get("folder"),
            note=target.get("note"),
        )
        session.tool_calls.append(asdict(result))
        if result.status != "ok":
            return "I could not save the findings to Obsidian."
        target_path = result.output.get("target", {}).get("path") or result.output.get("path")
        return f"Saved to Obsidian at `{target_path}`."

    def _memory_save_target(self, request_text: str, content_text: str, options: dict[str, Any]) -> dict[str, str]:
        explicit = self._explicit_memory_target(request_text) or self._explicit_memory_target(content_text)
        if explicit:
            return explicit
        folders = self.memory.folder_paths(max_depth=5)
        note_paths = [item.get("path", "") for item in self.memory.notes(limit=120).get("notes", []) if item.get("path")]
        deterministic_folder = self._deterministic_memory_folder(f"{request_text}\n\n{content_text}", folders)
        deterministic_note = self._deterministic_memory_note(request_text, content_text)
        target = {"folder": deterministic_folder, "note": deterministic_note}
        chooser = getattr(self.llm, "memory_save_target", None)
        if callable(chooser):
            suggestion = chooser(request_text, content_text, folders, note_paths, options)
            if isinstance(suggestion, dict):
                folder = str(suggestion.get("folder") or "").strip()
                note = str(suggestion.get("note") or "").strip()
                if folder and folder.lower().strip("/") not in {"inbox", "sessions"}:
                    target["folder"] = folder
                if note:
                    target["note"] = note
        return target

    def _memory_note_content_for_save(self, answer_text: str) -> str:
        text = (answer_text or "").strip()
        if not text:
            return text
        draft = self._extract_obsidian_note_draft(text)
        if draft:
            return draft
        text = re.sub(r"\n*Research provider:\s*`[^`]+`\s*$", "", text, flags=re.I).strip()
        text = re.sub(r"\n*Saved to Obsidian at\s+`[^`]+`\.\s*$", "", text, flags=re.I).strip()
        return text

    def _extract_obsidian_note_draft(self, text: str) -> str:
        marker = re.search(r"obsidian\s+note\s+draft", text, flags=re.I)
        if marker:
            tail = text[marker.end():]
            fenced = re.search(r"```(?:markdown|md)?\s*\n(.*?)\n```", tail, flags=re.I | re.S)
            if fenced:
                return fenced.group(1).strip()
        fenced_blocks = re.findall(r"```(?:markdown|md)\s*\n(.*?)\n```", text, flags=re.I | re.S)
        if len(fenced_blocks) == 1:
            block = fenced_blocks[0].strip()
            if block.startswith("#"):
                return block
        return ""

    def _explicit_memory_target(self, text: str) -> dict[str, str] | None:
        folder_match = re.search(r"(?:^|\n)\s*(?:folder|path)\s*:\s*(.+)\s*$", text, flags=re.I | re.M)
        note_match = re.search(r"(?:^|\n)\s*(?:note|file|title)\s*:\s*(.+)\s*$", text, flags=re.I | re.M)
        folder = folder_match.group(1).strip() if folder_match else ""
        note = note_match.group(1).strip() if note_match else ""
        if folder or note:
            return {"folder": folder or "", "note": note or self._deterministic_memory_note(text, text)}
        return None

    def _deterministic_memory_folder(self, text: str, folders: list[str]) -> str:
        candidates = [item.strip().strip("/") for item in folders if item and item.strip().strip("/")]
        candidates = [item for item in candidates if item.split("/")[0].lower() not in {"inbox", "sessions"}]
        terms = self._memory_route_terms(text)
        if not terms:
            return "Notes"
        best_folder = ""
        best_score = 0
        for folder in candidates:
            score = self._folder_route_score(folder, terms)
            if score > best_score or (score == best_score and best_folder and len(folder) < len(best_folder)):
                best_folder = folder
                best_score = score
        return best_folder if best_score > 0 else self._deterministic_new_memory_folder(text, terms)

    def _deterministic_new_memory_folder(self, text: str, terms: set[str]) -> str:
        research_terms = {
            "arxiv", "citation", "citations", "literature", "paper", "papers", "publication",
            "publications", "research", "sources", "study", "studies", "survey",
        }
        if terms.intersection(research_terms):
            return "Research"
        heading = re.search(r"^\s*#\s+(.+)$", text, flags=re.M)
        source = heading.group(1) if heading else text
        source = re.sub(r"\b(latest|recent|summary|notes?|findings|details?|overview)\b", " ", source, flags=re.I)
        source = re.sub(r"\b(and|then)\s+(save|document|store|remember)\b.*$", "", source, flags=re.I)
        words = [
            word
            for word in re.findall(r"[A-Za-z0-9]+", source)
            if word.lower() not in {
                "save", "document", "remember", "obsidian", "vault", "please", "sources",
                "the", "user", "users", "memory", "prefers", "prefer",
            }
        ][:4]
        if not words:
            return "Notes"
        return " ".join(words).strip().title()

    def _folder_route_score(self, folder: str, terms: set[str]) -> int:
        lower = folder.lower()
        parts = [part.lower() for part in folder.split("/")]
        score = 0
        for term in terms:
            if term in parts:
                score += 8
            elif term in lower:
                score += 3
        research_terms = {
            "arxiv", "citation", "citations", "literature", "paper", "papers", "publication",
            "publications", "research", "sources", "study", "studies", "survey",
        }
        if "research" in parts and terms.intersection(research_terms):
            score += 6
        project_terms = {"project", "projects", "build", "implementation", "roadmap", "milestone"}
        if "projects" in parts and terms.intersection(project_terms):
            score += 4
        skill_terms = {"skill", "skills", "workflow", "instructions", "tool", "tools"}
        if "skills" in parts and terms.intersection(skill_terms):
            score += 4
        decision_terms = {"decision", "decisions", "choose", "chosen", "tradeoff", "architecture"}
        if "decisions" in parts and terms.intersection(decision_terms):
            score += 4
        return score

    def _memory_route_terms(self, text: str) -> set[str]:
        stopwords = {
            "about", "above", "after", "also", "and", "answer", "assistant", "can", "could",
            "details", "document", "find", "from", "into", "latest", "memory", "note", "notes",
            "obsidian", "please", "provided", "request", "save", "saved", "source", "that", "the",
            "them", "this", "those", "user", "vault", "with", "would", "you",
        }
        return {
            term.lower()
            for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)
            if term.lower() not in stopwords
        }

    def _deterministic_memory_note(self, request_text: str, content_text: str) -> str:
        heading = re.search(r"^\s*#\s+(.+)$", content_text, flags=re.M)
        if heading:
            return f"{self._slug(heading.group(1))}.md"
        title_source = request_text or content_text
        title_source = re.sub(r"\b(in|into)\s+my\s+(obsidian|vault|notes?)\b", "", title_source, flags=re.I)
        title_source = re.sub(
            r"^\s*(can you|could you|please|pls|would you|find|look up|search|research|save|document|remember)\b[:\s-]*",
            "",
            title_source,
            flags=re.I,
        )
        title_source = re.sub(r"\b(and|then)\s+(save|document|store|remember)\b.*$", "", title_source, flags=re.I)
        words = re.findall(r"[A-Za-z0-9]+", title_source)[:8]
        return f"{self._slug(' '.join(words) or 'note')}.md"

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
        return slug or "note"

    def _route_llm_selected_tool(self, session: Session, content: str, options: dict[str, Any]) -> str | None:
        if not hasattr(self.llm, "select_tool"):
            return None
        selection = self.llm.select_tool(content, self._llm_selectable_tools(), options)
        if not selection:
            return None
        result = self._execute_selected_tool(session, selection, content, options)
        if result is None:
            return None
        return self._answer_for_one_shot_tool_result(content, result, options)

    def _run_agentic_tool_loop(self, session: Session, content: str, options: dict[str, Any]) -> str | None:
        if not hasattr(self.llm, "agent_next_action"):
            return self._route_llm_selected_tool(session, content, options)

        tools = self._llm_selectable_tools()
        request_context = self._agentic_request_context(session, content)
        observations: list[dict[str, Any]] = []
        for _ in range(6):
            action = self.llm.agent_next_action(request_context, tools, observations, options)
            if not action:
                return self._route_llm_selected_tool(session, content, options) if not observations else self._fallback_tool_loop_answer(content, observations)

            if action.get("action") == "answer":
                answer = str(action.get("answer") or "").strip()
                if not observations:
                    return None
                return answer or None

            if action.get("action") != "tool":
                return None

            result = self._execute_selected_tool(session, action, content, options)
            if result is None:
                observations.append({
                    "tool": action.get("tool"),
                    "arguments": action.get("arguments") or {},
                    "status": "error",
                    "output": {"error": "tool call was invalid or unavailable"},
                })
                continue
            observations.append(self._compact_tool_observation(result))

        return self._fallback_tool_loop_answer(content, observations)

    def _agentic_request_context(self, session: Session, content: str) -> str:
        prior_messages = session.messages[:-1][-6:]
        prior_tools = session.tool_calls[-8:]
        context: dict[str, Any] = {
            "current_user_request": content,
            "recent_messages": prior_messages,
            "recent_tool_calls": [self._compact_prior_tool_call(call) for call in prior_tools],
        }
        return (
            "Use this conversation context to resolve references like it, that folder, the file, or the previous result.\n"
            + json.dumps(context, ensure_ascii=False)[:12000]
        )

    def _compact_prior_tool_call(self, call: dict[str, Any]) -> dict[str, Any]:
        output = call.get("output") or {}
        if call.get("name") == "file_find":
            output = {
                "matches": (output.get("matches") or [])[:20],
                "searched_roots": output.get("searched_roots") or [],
                "truncated": output.get("truncated"),
            }
        elif call.get("name") == "file_list":
            output = {
                "path": output.get("path"),
                "entries": (output.get("entries") or [])[:40],
                "truncated": output.get("truncated"),
            }
        elif call.get("name") == "file_read":
            output = {
                "path": output.get("path"),
                "text": str(output.get("text") or "")[:1200],
                "error": output.get("error"),
            }
        return {
            "name": call.get("name"),
            "status": call.get("status"),
            "input": call.get("input") or {},
            "output": output,
        }

    def _execute_selected_tool(self, session: Session, selection: dict[str, Any], content: str, options: dict[str, Any]) -> Any | None:
        tool = selection.get("tool")
        arguments = dict(selection.get("arguments") or {})
        if tool == "memory_search":
            selected_query = str(arguments.get("query") or content)
            search_query = self._memory_search_query(selected_query, options)
            result = self.tools.call("memory_search", query=search_query, original_query=content, limit=6)
            session.tool_calls.append(asdict(result))
            return result
        if tool == "browser_fetch":
            url = str(arguments.get("url") or "").strip()
            if not url:
                return None
            result = self.tools.call("browser_fetch", url=url)
            session.tool_calls.append(asdict(result))
            return result
        if tool == "browser_search":
            query = str(arguments.get("query") or content).strip()
            limit = int(arguments.get("limit") or 6)
            result = self.tools.call("browser_search", query=query, limit=limit, include_content=True)
            session.tool_calls.append(asdict(result))
            return result
        if tool == "file_read":
            path = str(arguments.get("path") or "").strip()
            if not path:
                return None
            result = self.tools.call("file_read", path=path)
            session.tool_calls.append(asdict(result))
            return result
        if tool == "file_list":
            path = str(arguments.get("path") or ".").strip() or "."
            result = self.tools.call("file_list", path=path, limit=int(arguments.get("limit") or 80))
            session.tool_calls.append(asdict(result))
            return result
        if tool == "file_find":
            query = str(arguments.get("query") or arguments.get("name") or "").strip()
            if not query:
                return None
            path = str(arguments.get("path") or "").strip()
            kind = str(arguments.get("kind") or "any").strip().lower()
            result = self.tools.call("file_find", query=query, path=path, kind=kind, limit=int(arguments.get("limit") or 80), max_depth=int(arguments.get("max_depth") or 10))
            session.tool_calls.append(asdict(result))
            return result
        if tool == "computer_status":
            result = self.tools.call("computer_status")
            session.tool_calls.append(asdict(result))
            return result
        if tool == "computer_list_apps":
            result = self.tools.call("computer_list_apps")
            session.tool_calls.append(asdict(result))
            return result
        if tool == "computer_inspect":
            app = str(arguments.get("app") or "").strip()
            if not app:
                return None
            result = self.tools.call("computer_inspect", app=app, max_depth=3, max_children=60)
            session.tool_calls.append(asdict(result))
            return result
        return None

    def _answer_for_one_shot_tool_result(self, content: str, result: Any, options: dict[str, Any]) -> str:
        if result.name == "memory_search":
            if result.status != "ok":
                return f"I could not search memory: {result.output}"
            return self._answer_memory_search(None, content, result.output, options)
        if result.name == "browser_fetch":
            if result.status == "ok":
                text = result.output.get("text", "")
                return f"Fetched `{result.input.get('url')}`.\n\n{text[:2500]}"
            return f"Fetch failed: {result.output}"
        if result.name == "browser_search":
            if result.status != "ok":
                return f"Research failed: {result.output}"
            return self._answer_web_research(str(result.input.get("query") or content), result.output, options)
        if result.name == "file_read":
            if result.status == "ok":
                return f"Read `{result.output['path']}`.\n\n{result.output['text']}"
            return f"Read failed: {result.output}"
        if result.name == "file_list":
            if result.status != "ok":
                return f"List failed: {result.output}"
            return self._format_file_list(result.output)
        if result.name == "file_find":
            if result.status != "ok":
                return f"Find failed: {result.output}"
            return self._format_file_find(str(result.input.get("query") or ""), result.output)
        if result.name == "computer_status":
            return self._format_computer_status(result.output)
        if result.name == "computer_list_apps":
            return self._format_computer_apps(result)
        if result.name == "computer_inspect":
            if result.status == "ok":
                return f"Inspected `{result.input.get('app')}`.\n\n```plaintext\n{result.output.get('tree', '').strip()}\n```"
            return f"Inspect failed: {result.output}"
        return str(result.output)

    def _compact_tool_observation(self, result: Any) -> dict[str, Any]:
        output = result.output
        if result.name == "file_find":
            output = {
                "matches": (result.output.get("matches") or [])[:30],
                "searched_roots": result.output.get("searched_roots") or [],
                "truncated": result.output.get("truncated"),
                "visited": result.output.get("visited"),
            }
        elif result.name == "file_list":
            output = {
                "path": result.output.get("path"),
                "entries": (result.output.get("entries") or [])[:80],
                "truncated": result.output.get("truncated"),
                "allowed_roots": result.output.get("allowed_roots") or [],
            }
        elif result.name == "file_read":
            output = {
                "path": result.output.get("path"),
                "text": str(result.output.get("text") or "")[:3000],
                "error": result.output.get("error"),
            }
        elif result.name == "browser_search":
            output = {
                "results": (result.output.get("results") or [])[:6],
                "error": result.output.get("error"),
            }
        return {
            "tool": result.name,
            "arguments": result.input,
            "status": result.status,
            "output": output,
        }

    def _fallback_tool_loop_answer(self, content: str, observations: list[dict[str, Any]]) -> str | None:
        if not observations:
            return None
        latest = observations[-1]
        if latest.get("tool") == "file_find" and latest.get("status") == "ok":
            return self._format_file_find(str((latest.get("arguments") or {}).get("query") or ""), latest.get("output") or {})
        if latest.get("tool") == "file_list" and latest.get("status") == "ok":
            return self._format_file_list(latest.get("output") or {})
        if latest.get("tool") == "file_read" and latest.get("status") == "ok":
            output = latest.get("output") or {}
            return f"Read `{output.get('path')}`.\n\n{str(output.get('text') or '')[:3000]}"
        return f"I tried to use local tools for `{content}`, but could not produce a final answer. Last observation: `{latest}`"

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
                "name": "browser_search",
                "description": "Search the web for fresh sources on a topic and return top results with links.",
                "arguments": {"query": "topic to research", "limit": "optional result count"},
            },
            {
                "name": "file_read",
                "description": "Read a local file path when the user asks to inspect that file.",
                "arguments": {"path": "path inside an allowed root"},
            },
            {
                "name": "file_list",
                "description": "List files and folders in a local directory inside an allowed root. Use after finding a promising folder to inspect its contents.",
                "arguments": {"path": "directory path inside an allowed root, or . for the default root"},
            },
            {
                "name": "file_find",
                "description": "Recursively find files or folders by name across allowed local roots. Use broad literal name fragments such as insurance, invoice, health, passport, or pdf; optionally constrain path to ~/Desktop, ~/Documents, or a matched folder.",
                "arguments": {"query": "file or folder name fragment to find", "kind": "any, file, or directory", "path": "optional allowed root/subfolder"},
            },
            {
                "name": "computer_status",
                "description": "Check whether experimental macOS Computer Use is available and what permissions it needs.",
                "arguments": {},
            },
            {
                "name": "computer_list_apps",
                "description": "List visible macOS apps that Computer Use may be able to inspect or control.",
                "arguments": {},
            },
            {
                "name": "computer_inspect",
                "description": "Inspect one named macOS app and return its accessibility tree for visible UI controls.",
                "arguments": {"app": "app name such as Spotify, Finder, Chrome, or Obsidian"},
            },
        ]

    def _memory_search_query(self, content: str, options: dict[str, Any]) -> str:
        if hasattr(self.llm, "memory_search_query"):
            query = self.llm.memory_search_query(content, options)
            if query:
                return query
        return content

    def _route_file_list(self, session: Session, path: str = ".") -> str:
        result = self.tools.call("file_list", path=path or ".", limit=80)
        session.tool_calls.append(asdict(result))
        if result.status != "ok":
            return f"List failed: {result.output}"
        return self._format_file_list(result.output)

    def _route_file_find(self, session: Session, query: str, path: str = "", kind: str = "any") -> str:
        result = self.tools.call("file_find", query=query, path=path, kind=kind, limit=80, max_depth=10)
        session.tool_calls.append(asdict(result))
        if result.status != "ok":
            return f"Find failed: {result.output}"
        return self._format_file_find(query, result.output)

    def _format_file_list(self, output: dict[str, Any]) -> str:
        entries = output.get("entries") or []
        lines = [f"I can see this directory: `{output.get('path', '.')}`"]
        if not entries:
            lines.append("\nNo visible files or folders found there.")
        else:
            lines.append("")
            for item in entries:
                icon = "dir" if item.get("type") == "directory" else "file"
                lines.append(f"- `{item.get('name')}` ({icon})")
        roots = output.get("allowed_roots") or []
        if roots:
            lines.extend(["", "Allowed roots:"])
            lines.extend(f"- `{root}`" for root in roots)
        if output.get("truncated"):
            lines.append("\nOutput was truncated. Use `/ls <path>` for a narrower directory.")
        return "\n".join(lines)

    def _format_file_find(self, query: str, output: dict[str, Any]) -> str:
        matches = output.get("matches") or []
        lines = [f"Search results for `{query}`:"]
        if not matches:
            lines.append("\nNo matching files or folders found under the allowed roots.")
        else:
            lines.append("")
            for item in matches:
                icon = "dir" if item.get("type") == "directory" else "file"
                lines.append(f"- `{item.get('path')}` ({icon})")
        roots = output.get("searched_roots") or []
        if roots:
            lines.extend(["", "Searched roots:"])
            lines.extend(f"- `{root}`" for root in roots)
        if output.get("truncated"):
            lines.append("\nOutput was truncated. Use a narrower query or `/find <name> in <path>`.")
        return "\n".join(lines)

    def _is_file_list_request(self, lowered: str) -> bool:
        action = r"\b(list|show|see|view|display)\b"
        target = r"\b(files?|folders?|directories)\b"
        return bool(
            re.search(fr"{action}.*{target}", lowered)
            or re.search(fr"{target}.*\b(visible|available|present|there|see)\b", lowered)
        )

    def _is_file_find_request(self, lowered: str) -> bool:
        action = r"\b(find|locate|search for|look for)\b"
        target = r"\b(files?|folders?|directories)\b"
        return bool(re.search(fr"{action}.*{target}", lowered) or re.search(fr"{target}.*{action}", lowered))

    def _file_list_path_from_request(self, content: str) -> str:
        match = re.search(r"\b(?:in|under|inside)\s+(`[^`]+`|\"[^\"]+\"|'[^']+'|/[^\n?]+|~[^\n?]+)", content, flags=re.I)
        if not match:
            return "."
        path = match.group(1).strip().strip("`\"'")
        return path.strip() or "."

    def _file_find_params_from_request(self, content: str) -> dict[str, str]:
        return {
            "query": self._file_find_query_from_request(content),
            "path": self._file_find_path_from_request(content),
            "kind": self._file_find_kind_from_request(content),
        }

    def _file_find_kind_from_request(self, content: str) -> str:
        lower = content.lower()
        action_tail = re.split(r"\b(?:find|locate|search for|look for)\b", lower, maxsplit=1)
        target_text = action_tail[1] if len(action_tail) > 1 else lower
        if re.search(r"\b(folders?|directories)\b", target_text):
            return "directory"
        if re.search(r"\bfiles?\b", target_text):
            return "file"
        return "any"

    def _file_find_path_from_request(self, content: str) -> str:
        explicit = re.search(r"\b(?:in|under|inside)\s+(`[^`]+`|\"[^\"]+\"|'[^']+'|/[^\n?]+|~[^\n?]+)", content, flags=re.I)
        if explicit:
            return explicit.group(1).strip().strip("`\"'").strip()

        prefix = re.split(r"\b(?:and\s+)?(?:find|locate|search for|look for)\b", content, maxsplit=1, flags=re.I)[0]
        location_pattern = r"(desktop|documents|downloads)"
        folder_name = None
        location = None
        patterns = [
            fr"\b(?:my|the)?\s*([A-Za-z0-9_. -]+?)\s+(?:folder|directory)\s+(?:under|inside|in)\s+(?:my|the)?\s*{location_pattern}\b",
            fr"\b(?:folder|directory)\s+(?:named|called|name)\s+([A-Za-z0-9_. -]+?)\s+(?:under|inside|in)\s+(?:my|the)?\s*{location_pattern}\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, prefix, flags=re.I)
            if match:
                folder_name = self._clean_container_phrase(match.group(1))
                location = match.group(2).lower()
                break
        if not folder_name or not location:
            return ""
        aliases = {
            "desktop": "~/Desktop",
            "documents": "~/Documents",
            "downloads": "~/Downloads",
        }
        return f"{aliases[location]}/{folder_name}"

    def _file_find_query_from_request(self, content: str) -> str:
        action_match = re.search(
            r"\b(?:find|locate|search for|look for)\s+(?:any\s+|a\s+|an\s+|the\s+)?"
            r"(?:files?|folders?|directories)?\s*(?:named|called|name)\s+"
            r"(`[^`]+`|\"[^\"]+\"|'[^']+'|[A-Za-z0-9_. -]+?)"
            r"(?=\s+(?:in|under|inside|within|beneath)\b|\?|\.|$)",
            content,
            flags=re.I,
        )
        if action_match:
            return self._clean_file_phrase(action_match.group(1))

        action_match = re.search(
            r"\b(?:find|locate|search for|look for)\s+(?:any\s+|a\s+|an\s+|the\s+)?"
            r"(`[^`]+`|\"[^\"]+\"|'[^']+'|[A-Za-z0-9_. -]+?)\s+"
            r"(?:files?|folders?|directories)\b",
            content,
            flags=re.I,
        )
        if action_match:
            return self._clean_file_phrase(action_match.group(1))

        match = re.search(
            r"\b(?:named|called|matching|for)\s+(`[^`]+`|\"[^\"]+\"|'[^']+'|[A-Za-z0-9_. -]+?)"
            r"(?=\s+(?:in|under|inside|within|beneath)\b|\?|\.|$)",
            content,
            flags=re.I,
        )
        if match:
            return self._clean_file_phrase(match.group(1))
        cleaned = re.sub(r"\b(can you|could you|please|pls|find|locate|search for|look for|recursively|recursive|files?|folders?|directories|on my system|across|allowed roots|root folders)\b", " ", content, flags=re.I)
        cleaned = re.sub(r"\b(in|under|inside)\s+(`[^`]+`|\"[^\"]+\"|'[^']+'|/[^\n?]+|~[^\n?]+)", " ", cleaned, flags=re.I)
        return " ".join(cleaned.strip(" ?").split())

    def _clean_file_phrase(self, phrase: str) -> str:
        cleaned = phrase.strip().strip("`\"' .?")
        cleaned = re.sub(r"^(?:my|the|a|an)\s+", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    def _clean_container_phrase(self, phrase: str) -> str:
        cleaned = self._clean_file_phrase(phrase)
        cleaned = re.sub(r"^.*\b(?:check|inspect|open|use)\s+(?:my|the|a|an)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"^(?:recursively|recursive)\s+", "", cleaned, flags=re.I)
        return self._clean_file_phrase(cleaned)

    def _format_browser_search(self, query: str, output: dict[str, Any]) -> str:
        results = output.get("results") or []
        if not results:
            return f"I searched the web for `{query}` but found no results."
        lines = [f"Top web results for `{query}`:", ""]
        for index, item in enumerate(results, start=1):
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            lines.append(f"{index}. {title} - {url}")
        return "\n".join(lines)

    def _answer_web_research(self, query: str, output: dict[str, Any], options: dict[str, Any]) -> str:
        results = output.get("results") or []
        if not results:
            return self._format_browser_search(query, output)
        source_context = self._web_research_context(output)
        prompt = (
            "Synthesize a web research answer using only the provided source material.\n"
            "Rules:\n"
            "- Start with the direct answer or findings.\n"
            "- Cite sources inline using [1], [2], etc. where relevant.\n"
            "- Include a short Sources section with title and URL.\n"
            "- If source content is thin, say what could be verified from titles/snippets only.\n"
            "- Do not invent publication dates, claims, or paper details not present in the sources.\n\n"
            f"User research request: {query}"
        )
        try:
            result = self.llm.complete([{"role": "user", "content": prompt}], source_context, None, options)
            answer = str(result.get("text") or "").strip()
            if answer:
                engine = output.get("engine") or "web"
                return f"{answer}\n\nResearch provider: `{engine}`"
        except Exception:
            pass
        return self._format_browser_search(query, output)

    def _web_research_context(self, output: dict[str, Any]) -> str:
        chunks = []
        for index, item in enumerate((output.get("results") or [])[:6], start=1):
            title = str(item.get("title") or "Untitled").strip()
            url = str(item.get("url") or "").strip()
            description = str(item.get("description") or "").strip()
            markdown = str(item.get("markdown") or "").strip()
            body = markdown or description or "(No extracted content available.)"
            chunks.append(f"[{index}] {title}\nURL: {url}\nSnippet: {description}\nContent:\n{body[:3500]}")
        return "\n\n".join(chunks)

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
