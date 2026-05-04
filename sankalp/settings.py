from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sankalp.config import STATE_DIR


SETTINGS_PATH = STATE_DIR / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "provider": "local",
    "openai_model": "gpt-5.5",
    "gemini_model": "gemini-2.5-flash",
    "codex_model": "",
    "local_openai_base_url": "http://localhost:2276/v1",
    "local_openai_model": "",
}


def load_settings(include_secrets: bool = False) -> dict[str, Any]:
    settings = DEFAULT_SETTINGS.copy()
    if SETTINGS_PATH.exists():
        try:
            settings.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    if not include_secrets:
        settings.pop("openai_api_key", None)
        settings.pop("gemini_api_key", None)
        settings.pop("local_openai_api_key", None)
        settings["has_openai_api_key"] = bool(load_settings(include_secrets=True).get("openai_api_key"))
        settings["has_gemini_api_key"] = bool(load_settings(include_secrets=True).get("gemini_api_key"))
        settings["has_local_openai_api_key"] = bool(load_settings(include_secrets=True).get("local_openai_api_key"))
    return settings


def save_settings(update: dict[str, Any]) -> dict[str, Any]:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = load_settings(include_secrets=True)
    for key in ["provider", "openai_model", "gemini_model", "codex_model", "local_openai_base_url", "local_openai_model"]:
        if key in update:
            current[key] = str(update.get(key) or "").strip()
    for key in ["openai_api_key", "gemini_api_key", "local_openai_api_key"]:
        if key in update and str(update.get(key) or "").strip():
            current[key] = str(update[key]).strip()
    if update.get("clear_openai_api_key"):
        current.pop("openai_api_key", None)
    if update.get("clear_gemini_api_key"):
        current.pop("gemini_api_key", None)
    if update.get("clear_local_openai_api_key"):
        current.pop("local_openai_api_key", None)
    SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return load_settings()
