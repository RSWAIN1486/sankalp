from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote

from sankalp.config import MODEL, ROOT, SOUL_FILE
from sankalp.sessions.store import title_from_query
from sankalp.settings import load_settings


class LLMAdapter:
    def stream_complete(
        self,
        messages: list[dict[str, str]],
        memory_context: str,
        previous_response_id: str | None = None,
        options: dict[str, Any] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ):
        settings = self._settings_with_options(options or {})
        attachments = attachments or []
        provider = settings.get("provider", "local")
        if provider == "openai":
            api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
            if api_key:
                yield from self._openai_stream(api_key, settings, messages, memory_context, previous_response_id, attachments)
                return
        if provider == "local_openai":
            yield from self._local_openai_stream(settings, messages, memory_context, attachments)
            return
        if provider == "gemini":
            yield from self._gemini_stream(settings, messages, memory_context, attachments)
            return
        if provider == "codex":
            yield from self._codex_stream(settings, messages, memory_context)
            return
        result = self.complete(messages, memory_context, previous_response_id, options, attachments)
        text = str(result.get("text") or "")
        if text:
            yield {"type": "delta", "text": text}
        yield {"type": "response_id", "response_id": result.get("response_id"), "provider": result.get("provider")}

    def memory_search_query(self, message: str, options: dict[str, Any] | None = None) -> str | None:
        settings = self._settings_with_options(options or {})
        provider = settings.get("provider", "local")
        prompt = (
            "Rewrite this user request into a concise Obsidian memory search query.\n"
            "Return only JSON with this shape: {\"query\":\"...\"}.\n"
            "Keep important entities, product names, project names, concepts, metrics, methods, and dates.\n"
            "Remove conversational words and instructions to the assistant.\n"
            "Do not answer the user. Do not add facts not present in the request.\n\n"
            f"User request: {message.strip()[:2000]}"
        )
        messages = [{"role": "user", "content": prompt}]
        try:
            if provider == "local_openai":
                result = self._local_openai(settings, messages, "")
            elif provider == "gemini":
                result = self._gemini(settings, messages, "")
            elif provider == "codex":
                result = self._codex(settings, messages, "")
            elif provider == "openai":
                api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    return None
                result = self._openai(api_key, settings, messages, "", None)
            else:
                return None
        except Exception:
            return None
        return self._parse_memory_search_query(str(result.get("text") or ""))

    def memory_save_target(
        self,
        request: str,
        content: str,
        folders: list[str],
        existing_notes: list[str],
        options: dict[str, Any] | None = None,
    ) -> dict[str, str] | None:
        settings = self._settings_with_options(options or {})
        provider = settings.get("provider", "local")
        folder_text = "\n".join(f"- {item}" for item in folders[:200]) or "- Inbox"
        note_text = "\n".join(f"- {item}" for item in existing_notes[:120]) or "- (none)"
        prompt = (
            "Choose the best Obsidian save target for this note.\n"
            "Return only JSON with: {\"folder\":\"...\",\"note\":\"...\"}.\n"
            "Rules:\n"
            "- Prefer an existing folder when it semantically fits.\n"
            "- Use concise professional folder/note names.\n"
            "- Avoid conversational phrasing in filenames.\n"
            "- note must end with .md.\n"
            "- Do not use Inbox as a fallback.\n"
            "- If no existing folder has a clear semantic fit, create a new concise top-level folder under the vault.\n"
            "- Research papers, literature reviews, citations, source-backed web findings, and arXiv-style notes should prefer a Research folder when one exists.\n"
            "- If the note is research-like and no Research folder exists, choose folder Research.\n"
            "- Save only the durable note topic, not the user's conversational wording.\n\n"
            f"User request:\n{request[:1000]}\n\n"
            f"Content to save:\n{content[:2500]}\n\n"
            f"Existing folders:\n{folder_text}\n\n"
            f"Existing note paths:\n{note_text}"
        )
        messages = [{"role": "user", "content": prompt}]
        try:
            if provider == "local_openai":
                result = self._local_openai(settings, messages, "")
            elif provider == "gemini":
                result = self._gemini(settings, messages, "")
            elif provider == "codex":
                result = self._codex(settings, messages, "")
            elif provider == "openai":
                api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    return None
                result = self._openai(api_key, settings, messages, "", None)
            else:
                return None
        except Exception:
            return None
        return self._parse_memory_save_target(str(result.get("text") or ""))

    def prepare_memory_save(
        self,
        request: str,
        answer: str,
        folders: list[str],
        existing_notes: list[str],
        options: dict[str, Any] | None = None,
    ) -> dict[str, str] | None:
        settings = self._settings_with_options(options or {})
        provider = settings.get("provider", "local")
        prompt = (
            "Prepare an Obsidian save plan for this assistant result.\n"
            "Return only JSON with this shape: {\"folder\":\"...\",\"note\":\"...md\",\"content\":\"...\"}.\n\n"
            "Rules:\n"
            "- Honor the user's requested folder/path exactly when provided.\n"
            "- If the assistant answer names an intended Obsidian path, use that path exactly for folder and note.\n"
            "- Choose the closest existing folder from the provided folder list when it matches the request.\n"
            "- Preserve human-readable note titles in the note filename; .md is optional but preferred.\n"
            "- content must be only the note body to save. Remove wrapper text like 'I drafted...' and remove any 'Saved to Obsidian...' line.\n"
            "- If the answer contains a clean Markdown note draft, use that draft as content.\n"
            "- Do not default to Inbox when a specific folder/path is visible in the request or answer.\n\n"
            f"Existing folders:\n{json.dumps(folders[:200], ensure_ascii=False)}\n\n"
            f"Existing notes:\n{json.dumps(existing_notes[:200], ensure_ascii=False)}\n\n"
            f"User request:\n{request.strip()[:3000]}\n\n"
            f"Assistant answer:\n{answer.strip()[:18000]}"
        )
        messages = [{"role": "user", "content": prompt}]
        try:
            if provider == "local_openai":
                result = self._local_openai(settings, messages, "")
            elif provider == "gemini":
                result = self._gemini(settings, messages, "")
            elif provider == "codex":
                result = self._codex(settings, messages, "")
            elif provider == "openai":
                api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    return None
                result = self._openai(api_key, settings, messages, "", None)
            else:
                return None
        except Exception:
            return None
        return self._parse_memory_save_plan(str(result.get("text") or ""))

    def select_tool(self, message: str, tools: list[dict[str, Any]], options: dict[str, Any] | None = None) -> dict[str, Any] | None:
        settings = self._settings_with_options(options or {})
        provider = settings.get("provider", "local")
        tool_text = "\n".join(
            f"- {tool['name']}: {tool['description']} Args: {json.dumps(tool.get('arguments') or {})}"
            for tool in tools
        )
        prompt = (
            "Choose whether a local assistant tool should handle the user message before normal chat.\n"
            "Return only JSON. Use {\"tool\":\"none\",\"arguments\":{}} when no tool is needed.\n"
            "Only choose a listed tool. Do not invent tools.\n\n"
            f"Tools:\n{tool_text}\n\n"
            f"User message:\n{message.strip()[:2000]}"
        )
        messages = [{"role": "user", "content": prompt}]
        try:
            if provider == "local_openai":
                result = self._local_openai(settings, messages, "")
            elif provider == "gemini":
                result = self._gemini(settings, messages, "")
            elif provider == "codex":
                result = self._codex(settings, messages, "")
            elif provider == "openai":
                api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    return None
                result = self._openai(api_key, settings, messages, "", None)
            else:
                return None
        except Exception:
            return None
        return self._parse_tool_selection(str(result.get("text") or ""), {tool["name"] for tool in tools})

    def agent_next_action(
        self,
        message: str,
        tools: list[dict[str, Any]],
        observations: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        settings = self._settings_with_options(options or {})
        provider = settings.get("provider", "local")
        tool_text = "\n".join(
            f"- {tool['name']}: {tool['description']} Args: {json.dumps(tool.get('arguments') or {})}"
            for tool in tools
        )
        observation_text = json.dumps(observations[-8:], ensure_ascii=False)[:12000]
        prompt = (
            "You are the planning controller for Sankalp. Resolve the user's request by iterating over "
            "the available local tools when evidence is needed, then answer from the observations.\n"
            "Return only JSON with one of these shapes:\n"
            "{\"action\":\"tool\",\"tool\":\"file_find\",\"arguments\":{},\"rationale\":\"short reason\"}\n"
            "{\"action\":\"answer\",\"answer\":\"final answer to the user\"}\n\n"
            "Rules:\n"
            "- Use tools for local files, memory, web research, or computer state instead of guessing.\n"
            "- Choose one tool call at a time. After each observation, refine the next step.\n"
            "- For broad local-file requests, start with simple broad filename/folder searches, then list promising folders and refine. "
            "Do not give up after one noisy or empty search if alternate terms or a container path are obvious.\n"
            "- Keep tool arguments minimal and literal: for example query=\"insurance\", path=\"~/Desktop\", kind=\"any\".\n"
            "- Only choose a listed tool. Never invent tools. Do not ask the user to do work that a listed read/search tool can do.\n"
            "- Answer only when the observations are enough or no useful tool step remains.\n\n"
            f"Tools:\n{tool_text}\n\n"
            f"User request:\n{message.strip()[:3000]}\n\n"
            f"Observations so far:\n{observation_text if observations else '[]'}"
        )
        messages = [{"role": "user", "content": prompt}]
        try:
            if provider == "local_openai":
                result = self._local_openai(settings, messages, "")
            elif provider == "gemini":
                result = self._gemini(settings, messages, "")
            elif provider == "codex":
                result = self._codex(settings, messages, "")
            elif provider == "openai":
                api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    return None
                result = self._openai(api_key, settings, messages, "", None)
            else:
                return None
        except Exception:
            return None
        return self._parse_agent_action(str(result.get("text") or ""), {tool["name"] for tool in tools})

    def title_for_query(self, query: str, options: dict[str, Any] | None = None) -> str:
        settings = load_settings(include_secrets=True)
        fallback = title_from_query(query)
        prompt = (
            "Create a short chat title for this user message.\n"
            "Rules: 3 to 5 words. No quotes. No punctuation. Return only the title.\n\n"
            f"User message: {query.strip()[:1200]}"
        )
        messages = [{"role": "user", "content": prompt}]

        api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if api_key:
            try:
                title_settings = dict(settings)
                title_settings["openai_model"] = "gpt-5.4-nano"
                title_settings["reasoning_effort"] = "none"
                result = self._openai(api_key, title_settings, messages, "", None)
                return self._clean_title(result.get("text") or "", fallback)
            except Exception:
                pass

        if settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY"):
            try:
                title_settings = dict(settings)
                title_settings["gemini_model"] = "gemini-2.5-flash-lite"
                title_settings["reasoning_effort"] = "none"
                result = self._gemini(title_settings, messages, "")
                return self._clean_title(result.get("text") or "", fallback)
            except Exception:
                pass

        if (settings.get("local_openai_base_url") or "").strip() and (settings.get("local_openai_model") or "").strip():
            try:
                result = self._local_openai(settings, messages, "")
                text = str(result.get("text") or "")
                if not text.startswith("OpenAI-compatible endpoint provider is selected"):
                    return self._clean_title(text, fallback)
            except Exception:
                pass
        return fallback

    def test_provider(self, update: dict[str, Any]) -> dict[str, Any]:
        settings = load_settings(include_secrets=True)
        for key, value in update.items():
            if key.endswith("_api_key") and not str(value or "").strip():
                continue
            settings[key] = str(value or "").strip()
        provider = str(settings.get("provider") or "local")
        messages = [{"role": "user", "content": "Reply with exactly: hello"}]
        try:
            if provider == "local_openai":
                result = self._local_openai(settings, messages, "")
            elif provider == "gemini":
                result = self._gemini(settings, messages, "")
            elif provider == "codex":
                result = self._codex(settings, messages, "")
            elif provider == "openai":
                api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    return {"ok": False, "provider": provider, "error": "OpenAI API key is not configured."}
                result = self._openai(api_key, settings, messages, "", None)
            else:
                result = {
                    "text": self._fallback(messages, ""),
                    "response_id": None,
                    "provider": "local-fallback",
                }
        except Exception as exc:
            return {"ok": False, "provider": provider, "error": str(exc)}

        text = str(result.get("text") or "").strip()
        if result.get("provider") == "local-fallback":
            return {"ok": provider == "local", "provider": provider, "model": self._selected_model(settings), "text": text}
        if text.startswith("Codex provider failed:"):
            return {"ok": False, "provider": provider, "model": self._selected_model(settings), "error": text}
        return {"ok": bool(text), "provider": provider, "model": self._selected_model(settings), "text": text}

    def complete(
        self,
        messages: list[dict[str, str]],
        memory_context: str,
        previous_response_id: str | None = None,
        options: dict[str, Any] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        settings = self._settings_with_options(options or {})
        attachments = attachments or []
        messages = self._with_text_attachments(messages, attachments)
        provider = settings.get("provider", "local")
        if provider == "local_openai":
            return self._local_openai(settings, messages, memory_context, attachments)
        if provider == "gemini":
            return self._gemini(settings, messages, memory_context, attachments)
        if provider == "codex":
            return self._codex(settings, messages, memory_context)
        api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if provider == "openai" and api_key:
            return self._openai(api_key, settings, messages, memory_context, previous_response_id, attachments)
        if provider == "openai" and not api_key:
            return {
                "text": "OpenAI is selected, but no OpenAI API key is configured. Add one in Settings or choose Gemini/Codex.",
                "response_id": previous_response_id,
                "provider": "local-fallback",
            }
        if provider == "gemini":
            return {
                "text": "Gemini is selected, but no Gemini API key is configured. Add it in Settings.",
                "response_id": previous_response_id,
                "provider": "local-fallback",
            }
        if provider == "local":
            return {
                "text": self._fallback(messages, memory_context),
                "response_id": previous_response_id,
                "provider": "local-fallback",
            }
        return {
            "text": self._fallback(messages, memory_context),
            "response_id": previous_response_id,
            "provider": "local-fallback",
        }

    def _settings_with_options(self, options: dict[str, Any]) -> dict[str, Any]:
        settings = load_settings(include_secrets=True)
        provider = str(options.get("provider") or settings.get("provider") or "local")
        settings["provider"] = provider
        model = str(options.get("model") or "").strip()
        if provider == "codex" and model == "gpt-5.5-mini":
            model = ""
        if model:
            if provider == "openai":
                settings["openai_model"] = model
            elif provider == "gemini":
                settings["gemini_model"] = model
            elif provider == "codex":
                settings["codex_model"] = model
            elif provider == "local_openai":
                settings["local_openai_model"] = model
        effort = str(options.get("reasoning_effort") or "").strip()
        if effort and effort != "auto":
            settings["reasoning_effort"] = effort
        response_mode = str(options.get("response_mode") or "").strip()
        if response_mode:
            settings["response_mode"] = response_mode
        return settings

    def _chat_messages(self, messages: list[dict[str, Any]], memory_context: str, attachments: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        attachments = attachments or []
        latest_user_index = self._latest_user_index(messages)
        chat_messages: list[dict[str, Any]] = [{"role": "system", "content": self._developer_prompt(memory_context)}]
        media = self._media_attachments(attachments, include_pdf=False)
        for index, item in enumerate(messages[-20:]):
            role = "assistant" if item.get("role") == "assistant" else "user"
            content: Any = item.get("content", "")
            if index == latest_user_index and media:
                parts = [{"type": "text", "text": content}]
                parts.extend({"type": "image_url", "image_url": {"url": self._data_url(att)}} for att in media if att.get("kind") == "image")
                content = parts
            chat_messages.append({"role": role, "content": content})
        return chat_messages

    def _with_text_attachments(self, messages: list[dict[str, str]], attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        context = self._attachment_text_context(attachments)
        if not context:
            return list(messages)
        copied = [dict(item) for item in messages]
        for item in reversed(copied):
            if item.get("role") == "user":
                item["content"] = f"{item.get('content', '')}\n\n{context}"
                break
        return copied

    def _attachment_text_context(self, attachments: list[dict[str, Any]]) -> str:
        chunks = []
        for item in attachments:
            if item.get("kind") == "text" and item.get("text"):
                chunks.append(f"[Attachment: {item.get('name', 'file')}]\n{item.get('text')}")
            elif item.get("kind") in {"image", "pdf"}:
                chunks.append(f"[Attachment: {item.get('name', 'file')} ({item.get('type', item.get('kind'))}) sent as media input when supported.]")
        return "\n\n".join(chunks)

    def _media_attachments(self, attachments: list[dict[str, Any]], include_pdf: bool = True) -> list[dict[str, Any]]:
        kinds = {"image", "pdf"} if include_pdf else {"image"}
        return [item for item in attachments if item.get("kind") in kinds and item.get("data")]

    def _latest_user_index(self, messages: list[dict[str, Any]]) -> int:
        visible = messages[-20:]
        for index in range(len(visible) - 1, -1, -1):
            if visible[index].get("role") != "assistant":
                return index
        return len(visible) - 1

    def _data_url(self, attachment: dict[str, Any]) -> str:
        return f"data:{attachment.get('type') or 'application/octet-stream'};base64,{attachment.get('data') or ''}"

    def _chat_messages_text_only(self, messages: list[dict[str, str]], memory_context: str) -> list[dict[str, str]]:
        return [{"role": "system", "content": self._developer_prompt(memory_context)}] + [
            {"role": "assistant" if item.get("role") == "assistant" else "user", "content": item.get("content", "")}
            for item in messages[-20:]
        ]

    def _developer_prompt(self, memory_context: str) -> str:
        prompt = (
            "You are Sankalp, a warm, practical personal assistant with durable memory. "
            "Use the supplied memory context when relevant. Do not claim to remember "
            "something unless it appears in memory context or the current conversation. "
            "When it would genuinely help you understand the user better, ask one subtle "
            "profile question, but keep it natural and infrequent."
        )
        soul = self._soul_prompt()
        if soul:
            prompt += "\n\nAgent persona:\n" + soul
        if memory_context:
            prompt += "\n\nRelevant memory:\n" + memory_context
        return prompt

    def _soul_prompt(self) -> str:
        try:
            text = SOUL_FILE.read_text(encoding="utf-8")
        except Exception:
            return ""
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()
        if text == "# Sankalp Agent Persona":
            return ""
        return text[:4000]

    def _openai(
        self,
        api_key: str,
        settings: dict[str, Any],
        messages: list[dict[str, Any]],
        memory_context: str,
        previous_response_id: str | None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": settings.get("openai_model") or MODEL,
            "input": self._openai_input(messages, memory_context, attachments or []),
            "store": True,
        }
        effort = settings.get("reasoning_effort")
        if effort and effort != "none":
            payload["reasoning"] = {"effort": effort}
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        return {
            "text": self._extract_text(data),
            "response_id": data.get("id"),
            "provider": "openai-responses",
        }

    def _openai_stream(
        self,
        api_key: str,
        settings: dict[str, Any],
        messages: list[dict[str, Any]],
        memory_context: str,
        previous_response_id: str | None,
        attachments: list[dict[str, Any]],
    ):
        payload: dict[str, Any] = {
            "model": settings.get("openai_model") or MODEL,
            "input": self._openai_input(messages, memory_context, attachments),
            "store": True,
            "stream": True,
        }
        effort = settings.get("reasoning_effort")
        if effort and effort != "none":
            payload["reasoning"] = {"effort": effort}
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        response_id = None
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                for event in self._iter_sse_json(response):
                    event_type = str(event.get("type") or "")
                    if event_type == "response.created":
                        response_id = event.get("response", {}).get("id") or event.get("id")
                    elif event_type in {"response.output_text.delta", "response.output_text.annotation.added"}:
                        delta = event.get("delta")
                        if isinstance(delta, str) and delta:
                            yield {"type": "delta", "text": delta}
                    elif event_type in {"response.reasoning_summary_text.delta", "response.reasoning.delta"}:
                        delta = event.get("delta")
                        if isinstance(delta, str) and delta:
                            yield {"type": "reasoning", "text": delta}
                    elif event_type == "response.completed":
                        response_id = event.get("response", {}).get("id") or response_id
                    elif event_type == "error":
                        message = event.get("error", {}).get("message") or "OpenAI streaming error."
                        raise RuntimeError(str(message))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI request failed: HTTP {exc.code} {detail}") from exc
        yield {"type": "response_id", "response_id": response_id, "provider": "openai-responses"}

    def _openai_input(self, messages: list[dict[str, Any]], memory_context: str, attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        latest_user_index = self._latest_user_index(messages)
        media = self._media_attachments(attachments)
        items: list[dict[str, Any]] = [{"role": "developer", "content": self._developer_prompt(memory_context)}]
        for index, item in enumerate(messages[-20:]):
            role = "assistant" if item.get("role") == "assistant" else "user"
            content: Any = item.get("content", "")
            if index == latest_user_index and media:
                parts = [{"type": "input_text", "text": content}]
                for attachment in media:
                    if attachment.get("kind") == "image":
                        parts.append({"type": "input_image", "image_url": self._data_url(attachment)})
                    elif attachment.get("kind") == "pdf":
                        parts.append({"type": "input_file", "filename": attachment.get("name") or "document.pdf", "file_data": attachment.get("data")})
                content = parts
            items.append({"role": role, "content": content})
        return items

    def _gemini(self, settings: dict[str, Any], messages: list[dict[str, Any]], memory_context: str, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return {
                "text": "Gemini is selected, but no Gemini API key is configured. Add it in Settings.",
                "response_id": None,
                "provider": "local-fallback",
            }
        attachments = attachments or []
        latest_user_index = self._latest_user_index(messages)
        media = self._media_attachments(attachments)
        contents = []
        for index, message in enumerate(messages[-20:]):
            role = "model" if message.get("role") == "assistant" else "user"
            parts = [{"text": message.get("content", "")}]
            if index == latest_user_index:
                parts.extend({
                    "inline_data": {
                        "mime_type": attachment.get("type") or "application/octet-stream",
                        "data": attachment.get("data") or "",
                    }
                } for attachment in media)
            contents.append({"role": role, "parts": parts})
        model = settings.get("gemini_model") or "gemini-2.5-flash"
        payload = {
            "systemInstruction": {"parts": [{"text": self._developer_prompt(memory_context)}]},
            "contents": contents,
        }
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        return {
            "text": self._extract_gemini_text(data),
            "response_id": None,
            "provider": "gemini",
        }

    def _local_openai(self, settings: dict[str, Any], messages: list[dict[str, Any]], memory_context: str, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        base_url = (settings.get("local_openai_base_url") or "").rstrip("/")
        model = (settings.get("local_openai_model") or "").strip()
        if not base_url:
            return {
                "text": "OpenAI-compatible endpoint provider is selected, but no base URL is configured.",
                "response_id": None,
                "provider": "local-openai",
            }
        if not model:
            return {
                "text": "OpenAI-compatible endpoint provider is selected, but no model is configured.",
                "response_id": None,
                "provider": "local-openai",
            }
        headers = {"Content-Type": "application/json"}
        api_key = (settings.get("local_openai_api_key") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": self._chat_messages(messages, memory_context, attachments),
            "stream": False,
        }
        if settings.get("response_mode") == "grounded_memory_answer":
            payload["temperature"] = 0
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
        return {
            "text": self._extract_chat_text(data),
            "response_id": data.get("id"),
            "provider": "local-openai",
        }

    def _local_openai_stream(self, settings: dict[str, Any], messages: list[dict[str, Any]], memory_context: str, attachments: list[dict[str, Any]] | None = None):
        base_url = (settings.get("local_openai_base_url") or "").rstrip("/")
        model = (settings.get("local_openai_model") or "").strip()
        if not base_url:
            yield {"type": "delta", "text": "OpenAI-compatible endpoint provider is selected, but no base URL is configured."}
            yield {"type": "response_id", "response_id": None, "provider": "local-openai"}
            return
        if not model:
            yield {"type": "delta", "text": "OpenAI-compatible endpoint provider is selected, but no model is configured."}
            yield {"type": "response_id", "response_id": None, "provider": "local-openai"}
            return
        headers = {"Content-Type": "application/json"}
        api_key = (settings.get("local_openai_api_key") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": self._chat_messages(messages, memory_context, attachments),
            "stream": True,
        }
        if settings.get("response_mode") == "grounded_memory_answer":
            payload["temperature"] = 0
        request = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        response_id = None
        emitted_text = False
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                for event in self._iter_sse_json(response):
                    if isinstance(event, str) and event == "[DONE]":
                        break
                    if not isinstance(event, dict):
                        continue
                    response_id = event.get("id") or response_id
                    for choice in event.get("choices") or []:
                        delta = (choice.get("delta") or {}).get("content")
                        if isinstance(delta, str) and delta:
                            emitted_text = True
                            yield {"type": "delta", "text": delta}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI-compatible request failed: HTTP {exc.code} {detail}") from exc
        if not emitted_text:
            result = self._local_openai(settings, messages, memory_context, attachments)
            text = str(result.get("text") or "")
            if text:
                yield {"type": "delta", "text": text}
            response_id = result.get("response_id") or response_id
        yield {"type": "response_id", "response_id": response_id, "provider": "local-openai"}

    def _codex(self, settings: dict[str, Any], messages: list[dict[str, str]], memory_context: str) -> dict[str, Any]:
        codex_command, codex_env = self._codex_cli()
        if not codex_command:
            return {
                "text": "Codex CLI is selected, but the `codex` command was not found on this daemon's PATH. Install Codex CLI or choose another default provider in Settings -> Provider.",
                "response_id": None,
                "provider": "codex",
            }
        transcript = "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in messages[-12:])
        prompt = (
            self._developer_prompt(memory_context)
            + "\n\nRespond to the latest user message as a personal assistant. "
            + "If the user asks to save something to Obsidian, provide content suitable for memory capture.\n\nTranscript:\n"
            + transcript
        )
        with tempfile.NamedTemporaryFile(prefix="sankalp-codex-", suffix=".txt") as output:
            command = [
                codex_command,
                "exec",
                "--sandbox",
                "read-only",
                "--cd",
                str(ROOT),
                "--skip-git-repo-check",
                "--ephemeral",
                "--color",
                "never",
                "--output-last-message",
                output.name,
            ]
            model = (settings.get("codex_model") or "").strip()
            if model:
                command.extend(["-m", model])
            effort = str(settings.get("reasoning_effort") or "").strip()
            if effort and effort != "none":
                command.extend(["-c", f'model_reasoning_effort="{effort}"'])
            command.append("-")
            proc = subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=180, env=codex_env)
            text = output.read().decode("utf-8", errors="replace").strip()
        if not text:
            stderr_text = self._filter_codex_stderr_text(proc.stderr or "")
            text = (proc.stdout or stderr_text or "Codex returned no response.").strip()
        if proc.returncode != 0:
            text = "Codex provider failed:\n\n" + text
        return {
            "text": text,
            "response_id": None,
            "provider": "codex",
        }

    def _gemini_stream(self, settings: dict[str, Any], messages: list[dict[str, Any]], memory_context: str, attachments: list[dict[str, Any]] | None = None):
        api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            yield {"type": "delta", "text": "Gemini is selected, but no Gemini API key is configured. Add it in Settings."}
            yield {"type": "response_id", "response_id": None, "provider": "local-fallback"}
            return
        attachments = attachments or []
        latest_user_index = self._latest_user_index(messages)
        media = self._media_attachments(attachments)
        contents = []
        for index, message in enumerate(messages[-20:]):
            role = "model" if message.get("role") == "assistant" else "user"
            parts = [{"text": message.get("content", "")}]
            if index == latest_user_index:
                parts.extend({
                    "inline_data": {
                        "mime_type": attachment.get("type") or "application/octet-stream",
                        "data": attachment.get("data") or "",
                    }
                } for attachment in media)
            contents.append({"role": role, "parts": parts})
        model = settings.get("gemini_model") or "gemini-2.5-flash"
        payload = {
            "systemInstruction": {"parts": [{"text": self._developer_prompt(memory_context)}]},
            "contents": contents,
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:" \
              f"streamGenerateContent?alt=sse&key={quote(str(api_key), safe='')}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        emitted = False
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                for event in self._iter_sse_json(response):
                    if not isinstance(event, dict):
                        continue
                    text = self._extract_gemini_text(event)
                    if text:
                        emitted = True
                        yield {"type": "delta", "text": text}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini request failed: HTTP {exc.code} {detail}") from exc
        if not emitted:
            yield {"type": "delta", "text": "Gemini returned no stream text."}
        yield {"type": "response_id", "response_id": None, "provider": "gemini"}

    def _codex_stream(self, settings: dict[str, Any], messages: list[dict[str, str]], memory_context: str):
        codex_command, codex_env = self._codex_cli()
        if not codex_command:
            yield {
                "type": "delta",
                "text": "Codex CLI is selected, but the `codex` command was not found on this daemon's PATH. Install Codex CLI or choose another default provider in Settings -> Provider.",
            }
            yield {"type": "response_id", "response_id": None, "provider": "codex"}
            return
        transcript = "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in messages[-12:])
        prompt = (
            self._developer_prompt(memory_context)
            + "\n\nRespond to the latest user message as a personal assistant. "
            + "If the user asks to save something to Obsidian, provide content suitable for memory capture.\n\nTranscript:\n"
            + transcript
        )
        with tempfile.NamedTemporaryFile(prefix="sankalp-codex-stream-", suffix=".txt") as output:
            command = [
                codex_command,
                "exec",
                "--json",
                "--sandbox",
                "read-only",
                "--cd",
                str(ROOT),
                "--skip-git-repo-check",
                "--ephemeral",
                "--color",
                "never",
                "--output-last-message",
                output.name,
                "-",
            ]
            model = (settings.get("codex_model") or "").strip()
            if model:
                command[2:2] = ["-m", model]
            effort = str(settings.get("reasoning_effort") or "").strip()
            if effort and effort != "none":
                command[2:2] = ["-c", f'model_reasoning_effort="{effort}"']
            proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=codex_env,
            )
            emitted = False
            try:
                assert proc.stdin is not None
                proc.stdin.write(prompt)
                proc.stdin.close()
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    kind = str(event.get("type") or "")
                    if "reason" in kind or "thinking" in kind:
                        delta = self._extract_codex_delta(event)
                        if delta:
                            yield {"type": "reasoning", "text": delta}
                    else:
                        delta = self._extract_codex_delta(event)
                        if delta:
                            emitted = True
                            yield {"type": "delta", "text": delta}
                proc.wait(timeout=300)
                if not emitted:
                    last_message = output.read().decode("utf-8", errors="replace").strip()
                    if last_message:
                        yield {"type": "delta", "text": last_message}
                    else:
                        fallback = self._extract_codex_fallback_from_stderr(proc)
                        if fallback:
                            yield {"type": "delta", "text": fallback}
                        else:
                            # Fallback to the known-working non-streaming Codex path.
                            recovered = self._codex(settings, messages, memory_context)
                            recovered_text = str(recovered.get("text") or "").strip()
                            if recovered_text:
                                yield {"type": "delta", "text": recovered_text}
                            elif proc.returncode != 0:
                                yield {"type": "delta", "text": "Codex provider failed with no stream output."}
            finally:
                if proc.poll() is None:
                    proc.kill()
        yield {"type": "response_id", "response_id": None, "provider": "codex"}

    def _codex_cli(self) -> tuple[str | None, dict[str, str]]:
        env = os.environ.copy()
        path_dirs = self._codex_path_dirs()
        env["PATH"] = os.pathsep.join(path_dirs)

        configured = (env.get("SANKALP_CODEX_BIN") or env.get("CODEX_CLI_PATH") or "").strip()
        if configured:
            configured_path = Path(configured).expanduser()
            if configured_path.is_file():
                parent = str(configured_path.parent)
                if parent not in path_dirs:
                    env["PATH"] = os.pathsep.join([parent, *path_dirs])
                return str(configured_path), env

        return shutil.which("codex", path=env["PATH"]), env

    def _codex_path_dirs(self) -> list[str]:
        candidates = [
            *os.environ.get("PATH", "").split(os.pathsep),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
            str(Path("~/.local/bin").expanduser()),
            str(Path("~/.npm-global/bin").expanduser()),
        ]
        candidates.extend(str(path) for path in sorted(Path("~/.nvm/versions/node").expanduser().glob("*/bin"), reverse=True))

        seen: set[str] = set()
        path_dirs: list[str] = []
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            path_dirs.append(candidate)
        return path_dirs

    def _extract_codex_delta(self, event: dict[str, Any]) -> str:
        candidates = [
            event.get("delta"),
            event.get("text"),
            event.get("content"),
            (event.get("data") or {}).get("delta") if isinstance(event.get("data"), dict) else None,
            (event.get("data") or {}).get("text") if isinstance(event.get("data"), dict) else None,
        ]
        for item in candidates:
            if isinstance(item, str) and item:
                return item
        message = event.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content:
                return content
            if isinstance(content, list):
                texts: list[str] = []
                for part in content:
                    if isinstance(part, dict):
                        text = part.get("text")
                        if isinstance(text, str) and text:
                            texts.append(text)
                if texts:
                    return "".join(texts)
        data = event.get("data")
        if isinstance(data, dict):
            msg = data.get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str) and content:
                    return content
                if isinstance(content, list):
                    texts: list[str] = []
                    for part in content:
                        if isinstance(part, dict):
                            text = part.get("text")
                            if isinstance(text, str) and text:
                                texts.append(text)
                    if texts:
                        return "".join(texts)
        return ""

    def _extract_codex_fallback_from_stderr(self, proc: subprocess.Popen) -> str:
        try:
            stderr_text = proc.stderr.read() if proc.stderr else ""
        except Exception:
            return ""
        if not stderr_text:
            return ""
        lines = [line.strip() for line in self._filter_codex_stderr_text(stderr_text).splitlines() if line.strip()]
        if not lines:
            return ""
        return "\n".join(lines[-6:])

    def _filter_codex_stderr_text(self, text: str) -> str:
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        filtered: list[str] = []
        for line in lines:
            lower = line.lower()
            if "warning: no last agent message" in lower:
                continue
            if "wrote empty content to" in lower and ("sankalp-codex-stream-" in lower or "sankalp-codex-" in lower):
                continue
            filtered.append(line)
        return "\n".join(filtered)

    def _extract_text(self, data: dict[str, Any]) -> str:
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        parts: list[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip() or "I got a response, but could not extract text from it."

    def _extract_gemini_text(self, data: dict[str, Any]) -> str:
        parts: list[str] = []
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip() or "Gemini returned a response, but I could not extract text from it."

    def _extract_chat_text(self, data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if choices:
            content = choices[0].get("message", {}).get("content")
            if isinstance(content, str):
                return content.strip()
        return "The local OpenAI-compatible server responded, but I could not extract message content."

    def _iter_sse_json(self, response):
        for raw in response:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload:
                continue
            if payload == "[DONE]":
                yield payload
                continue
            try:
                yield json.loads(payload)
            except json.JSONDecodeError:
                continue

    def _selected_model(self, settings: dict[str, Any]) -> str:
        provider = str(settings.get("provider") or "local")
        if provider == "openai":
            return str(settings.get("openai_model") or MODEL)
        if provider == "gemini":
            return str(settings.get("gemini_model") or "gemini-3-flash-preview")
        if provider == "codex":
            return str(settings.get("codex_model") or "Codex default")
        if provider == "local_openai":
            return str(settings.get("local_openai_model") or "")
        return "local fallback"

    def _clean_title(self, value: str, fallback: str) -> str:
        lines = [line.strip() for line in str(value).splitlines() if line.strip()]
        title = lines[0] if lines else ""
        title = re.sub(r"^(chat\s+)?title\s*:\s*", "", title, flags=re.I)
        title = title.strip().strip("\"'`").strip(" .,:;!?")
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'&/-]*", title)
        if not words:
            return fallback
        return " ".join(words[:5])[:64]

    def _parse_tool_selection(self, value: str, allowed: set[str]) -> dict[str, Any] | None:
        text = value.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
        if fenced:
            text = fenced.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        tool = str(data.get("tool") or "").strip()
        if not tool or tool == "none" or tool not in allowed:
            return None
        arguments = data.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        return {"tool": tool, "arguments": arguments}

    def _parse_agent_action(self, value: str, allowed: set[str]) -> dict[str, Any] | None:
        text = value.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
        if fenced:
            text = fenced.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        action = str(data.get("action") or "").strip().lower()
        if action == "answer":
            answer = str(data.get("answer") or "").strip()
            return {"action": "answer", "answer": answer} if answer else None
        if action != "tool":
            return None
        tool = str(data.get("tool") or "").strip()
        if not tool or tool not in allowed:
            return None
        arguments = data.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        rationale = str(data.get("rationale") or "").strip()
        return {"action": "tool", "tool": tool, "arguments": arguments, "rationale": rationale}

    def _parse_memory_search_query(self, value: str) -> str | None:
        text = value.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
        if fenced:
            text = fenced.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        query = str(data.get("query") or "").strip()
        if len(query) < 3:
            return None
        return query[:300]

    def _parse_memory_save_target(self, value: str) -> dict[str, str] | None:
        text = value.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
        if fenced:
            text = fenced.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        folder = str(data.get("folder") or "").strip().strip("/")
        note = str(data.get("note") or "").strip()
        if not folder or len(folder) > 200:
            return None
        if not note or len(note) > 160:
            return None
        if "/" in note or "\\" in note:
            return None
        if not note.lower().endswith(".md"):
            note += ".md"
        return {"folder": folder, "note": note}

    def _parse_memory_save_plan(self, value: str) -> dict[str, str] | None:
        text = value.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.S)
        if fenced:
            text = fenced.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        folder = str(data.get("folder") or "").strip().strip("/")
        note = str(data.get("note") or "").strip()
        content = str(data.get("content") or "").strip()
        if len(folder) > 240 or len(note) > 180:
            return None
        if "/" in note or "\\" in note:
            return None
        if note and not note.lower().endswith(".md"):
            note += ".md"
        if not folder and not note and not content:
            return None
        return {"folder": folder, "note": note, "content": content}

    def _fallback(self, messages: list[dict[str, str]], memory_context: str) -> str:
        latest = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        if memory_context:
            return (
                "I saved this turn and found relevant memory, but no model key is configured yet.\n\n"
                f"Relevant memory:\n{memory_context}\n\n"
                f"Your message was: {latest}"
            )
        return (
            "I am running in local fallback mode because `OPENAI_API_KEY` is not set. "
            "I can still save memories and run explicit tools like `/remember`, `/fetch`, `/read`, and `/append`."
        )
