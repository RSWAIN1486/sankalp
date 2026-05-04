from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import urllib.request
from typing import Any

from sankalp.config import MODEL, ROOT
from sankalp.sessions.store import title_from_query
from sankalp.settings import load_settings


class LLMAdapter:
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
        if memory_context:
            prompt += "\n\nRelevant memory:\n" + memory_context
        return prompt

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

    def _codex(self, settings: dict[str, Any], messages: list[dict[str, str]], memory_context: str) -> dict[str, Any]:
        transcript = "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in messages[-12:])
        prompt = (
            self._developer_prompt(memory_context)
            + "\n\nRespond to the latest user message as a personal assistant. "
            + "Do not edit files or run project-changing commands.\n\nTranscript:\n"
            + transcript
        )
        with tempfile.NamedTemporaryFile(prefix="sankalp-codex-", suffix=".txt") as output:
            command = [
                "codex",
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
            proc = subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=180)
            text = output.read().decode("utf-8", errors="replace").strip()
        if not text:
            text = (proc.stdout or proc.stderr or "Codex returned no response.").strip()
        if proc.returncode != 0:
            text = "Codex provider failed:\n\n" + text
        return {
            "text": text,
            "response_id": None,
            "provider": "codex",
        }

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
            "I can still save memories and run explicit tools like `remember:`, `/fetch`, `/read`, and `/append`."
        )
