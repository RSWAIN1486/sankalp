from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


RISKY_TERMS = {
    "buy",
    "delete",
    "install",
    "pay",
    "purchase",
    "remove",
    "send",
    "share",
    "submit",
    "transfer",
    "unsubscribe",
}

SENSITIVE_TERMS = {
    "2fa",
    "api key",
    "auth code",
    "bank",
    "credit card",
    "otp",
    "passcode",
    "password",
    "secret",
    "token",
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""
    requires_confirmation: bool = False


class ComputerActionPolicy:
    """Small deterministic guardrail before OS-level actions are executed."""

    def decide(self, action: dict[str, Any], user_instruction: str) -> PolicyDecision:
        tool = str(action.get("tool") or "").strip()
        if tool in {"done", "blocked", "wait", "screenshot", "inspect_app", "list_apps", "open_app"}:
            return PolicyDecision(True)

        if bool(action.get("requires_confirmation")):
            return PolicyDecision(
                False,
                str(action.get("reason") or "The next computer-use action needs confirmation."),
                requires_confirmation=True,
            )

        text = f"{user_instruction}\n{json.dumps(self._risk_relevant_action(action), ensure_ascii=False)}".lower()
        if any(term in text for term in SENSITIVE_TERMS):
            return PolicyDecision(
                False,
                "This action may handle sensitive data, so Sankalp paused before executing it.",
                requires_confirmation=True,
            )

        if tool == "click" and self._looks_like_risky_target(action):
            return PolicyDecision(
                False,
                "This click target looks high impact, so Sankalp paused before executing it.",
                requires_confirmation=True,
            )

        return PolicyDecision(True)

    def _risk_relevant_action(self, action: dict[str, Any]) -> dict[str, Any]:
        return {
            key: action.get(key)
            for key in ["tool", "app", "target", "label", "description", "element_path", "text", "value", "key"]
            if action.get(key) is not None
        }

    def _looks_like_risky_target(self, action: dict[str, Any]) -> bool:
        target_text = " ".join(
            str(action.get(key) or "")
            for key in ["target", "label", "description"]
        ).lower()
        return bool(re.search(r"\b(delete|submit|send|pay|purchase|buy|share|remove|confirm)\b", target_text))
