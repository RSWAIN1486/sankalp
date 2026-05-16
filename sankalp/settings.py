from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sankalp.config import ROOT, STATE_DIR, VAULT_DIR


SETTINGS_PATH = STATE_DIR / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "provider": "local",
    "openai_model": "gpt-5.5",
    "gemini_model": "gemini-3-flash-preview",
    "codex_model": "",
    "local_openai_base_url": "http://localhost:2276/v1",
    "local_openai_model": "",
    "firecrawl_base_url": "",
    "searxng_base_url": "",
    "telegram_gateway_enabled": False,
    "telegram_allowed_users": "",
    "telegram_allow_all": False,
    "obsidian_vault_path": str(VAULT_DIR),
    "obsidian_workspace_path": "",
    "allowed_roots": "",
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
        settings.pop("firecrawl_api_key", None)
        settings.pop("telegram_bot_token", None)
        settings["has_openai_api_key"] = bool(load_settings(include_secrets=True).get("openai_api_key"))
        settings["has_gemini_api_key"] = bool(load_settings(include_secrets=True).get("gemini_api_key"))
        settings["has_local_openai_api_key"] = bool(load_settings(include_secrets=True).get("local_openai_api_key"))
        settings["has_firecrawl_api_key"] = bool(load_settings(include_secrets=True).get("firecrawl_api_key"))
        settings["has_telegram_bot_token"] = bool(load_settings(include_secrets=True).get("telegram_bot_token"))
    return settings


def save_settings(update: dict[str, Any]) -> dict[str, Any]:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = load_settings(include_secrets=True)
    for key in [
        "provider",
        "openai_model",
        "gemini_model",
        "codex_model",
        "local_openai_base_url",
        "local_openai_model",
        "firecrawl_base_url",
        "searxng_base_url",
        "telegram_allowed_users",
        "obsidian_vault_path",
        "obsidian_workspace_path",
        "allowed_roots",
    ]:
        if key in update:
            current[key] = str(update.get(key) or "").strip()
    for key in ["telegram_gateway_enabled", "telegram_allow_all"]:
        if key in update:
            current[key] = bool(update.get(key))
    for key in ["openai_api_key", "gemini_api_key", "local_openai_api_key", "firecrawl_api_key", "telegram_bot_token"]:
        if key in update and str(update.get(key) or "").strip():
            current[key] = str(update[key]).strip()
    if update.get("clear_openai_api_key"):
        current.pop("openai_api_key", None)
    if update.get("clear_gemini_api_key"):
        current.pop("gemini_api_key", None)
    if update.get("clear_local_openai_api_key"):
        current.pop("local_openai_api_key", None)
    if update.get("clear_firecrawl_api_key"):
        current.pop("firecrawl_api_key", None)
    if update.get("clear_telegram_bot_token"):
        current.pop("telegram_bot_token", None)
    SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return load_settings()


def allowed_roots_from_settings() -> list[Path]:
    env_configured = os.environ.get("SANKALP_ALLOWED_ROOTS")
    if env_configured:
        return _unique_existing_roots(_split_env_roots(env_configured))

    settings = load_settings(include_secrets=True)
    configured = str(settings.get("allowed_roots") or "").strip()
    if configured:
        roots = _split_saved_roots(configured)
    else:
        roots = [str(ROOT), str(settings.get("obsidian_vault_path") or VAULT_DIR)]
    return _unique_existing_roots(roots)


def _split_env_roots(value: str) -> list[str]:
    return [part.strip() for part in value.split(os.pathsep) if part.strip()]


def _split_saved_roots(value: str) -> list[str]:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return [line.strip() for line in normalized.split("\n") if line.strip()]


def _unique_existing_roots(values: list[str]) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for value in values:
        try:
            path = Path(value).expanduser().resolve()
        except Exception:
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        roots.append(path)
    return roots or [ROOT.resolve(), VAULT_DIR.resolve()]


def auto_detect_obsidian_vault(accessible_only: bool = True) -> str:
    vaults = discover_obsidian_vaults()
    if not vaults:
        return ""
    if accessible_only:
        vaults = [vault for vault in vaults if bool(vault.get("accessible"))]
        if not vaults:
            return ""
    return str(vaults[0].get("path") or "").strip()


def ensure_obsidian_vault_setting() -> dict[str, Any]:
    current = load_settings(include_secrets=True)
    configured = str(current.get("obsidian_vault_path") or "").strip()
    configured_ok = bool(configured and _can_list(Path(configured).expanduser()))
    if configured_ok:
        return load_settings()

    detected = auto_detect_obsidian_vault(accessible_only=True)
    if not detected:
        return load_settings()
    current["obsidian_vault_path"] = detected
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return load_settings()


def discover_obsidian_vaults() -> list[dict[str, Any]]:
    registry = Path("~/Library/Application Support/obsidian/obsidian.json").expanduser()
    if not registry.exists():
        return []
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except Exception:
        return []
    vaults = []
    for vault_id, value in (data.get("vaults") or {}).items():
        path = Path(str(value.get("path") or "")).expanduser()
        if not path:
            continue
        vaults.append({
            "id": vault_id,
            "path": str(path),
            "open": bool(value.get("open")),
            "accessible": _can_list(path),
        })
    return sorted(vaults, key=lambda item: (not item["open"], item["path"]))


def _can_list(path: Path) -> bool:
    try:
        next(path.iterdir(), None)
        return True
    except StopIteration:
        return True
    except Exception:
        return False
