from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from sankalp.config import MODEL


class LLMAdapter:
    def complete(self, messages: list[dict[str, str]], memory_context: str, previous_response_id: str | None = None) -> dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return {
                "text": self._fallback(messages, memory_context),
                "response_id": previous_response_id,
                "provider": "local-fallback",
            }
        return self._openai(api_key, messages, memory_context, previous_response_id)

    def _openai(self, api_key: str, messages: list[dict[str, str]], memory_context: str, previous_response_id: str | None) -> dict[str, Any]:
        developer = (
            "You are Sankalp, a warm, practical personal assistant with durable memory. "
            "Use the supplied memory context when relevant. Do not claim to remember "
            "something unless it appears in memory context or the current conversation."
        )
        if memory_context:
            developer += "\n\nRelevant memory:\n" + memory_context
        payload: dict[str, Any] = {
            "model": MODEL,
            "input": [{"role": "developer", "content": developer}] + messages[-20:],
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
