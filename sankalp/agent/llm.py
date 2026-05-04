from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.request
from typing import Any

from sankalp.config import MODEL, ROOT
from sankalp.settings import load_settings


class LLMAdapter:
    def complete(self, messages: list[dict[str, str]], memory_context: str, previous_response_id: str | None = None) -> dict[str, Any]:
        settings = load_settings(include_secrets=True)
        provider = settings.get("provider", "local")
        if provider == "local_openai":
            return self._local_openai(settings, messages, memory_context)
        if provider == "gemini":
            return self._gemini(settings, messages, memory_context)
        if provider == "codex":
            return self._codex(settings, messages, memory_context)
        api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if provider == "openai" and api_key:
            return self._openai(api_key, settings, messages, memory_context, previous_response_id)
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

    def _chat_messages(self, messages: list[dict[str, str]], memory_context: str) -> list[dict[str, str]]:
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

    def _openai(self, api_key: str, settings: dict[str, Any], messages: list[dict[str, str]], memory_context: str, previous_response_id: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": settings.get("openai_model") or MODEL,
            "input": [{"role": "developer", "content": self._developer_prompt(memory_context)}] + messages[-20:],
            "store": True,
        }
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

    def _gemini(self, settings: dict[str, Any], messages: list[dict[str, str]], memory_context: str) -> dict[str, Any]:
        api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return {
                "text": "Gemini is selected, but no Gemini API key is configured. Add it in Settings.",
                "response_id": None,
                "provider": "local-fallback",
            }
        contents = []
        for message in messages[-20:]:
            role = "model" if message.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.get("content", "")}]})
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

    def _local_openai(self, settings: dict[str, Any], messages: list[dict[str, str]], memory_context: str) -> dict[str, Any]:
        base_url = (settings.get("local_openai_base_url") or "").rstrip("/")
        model = (settings.get("local_openai_model") or "").strip()
        if not base_url:
            return {
                "text": "OpenAI-compatible local provider is selected, but no base URL is configured.",
                "response_id": None,
                "provider": "local-openai",
            }
        if not model:
            return {
                "text": "OpenAI-compatible local provider is selected, but no model is configured.",
                "response_id": None,
                "provider": "local-openai",
            }
        headers = {"Content-Type": "application/json"}
        api_key = (settings.get("local_openai_api_key") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": self._chat_messages(messages, memory_context),
            "stream": False,
        }
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
                "--ask-for-approval",
                "never",
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
