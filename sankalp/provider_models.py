from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from sankalp.settings import load_settings


OPENAI_FALLBACK = [
    {"id": "gpt-5.5", "label": "GPT-5.5"},
    {"id": "gpt-5.5-mini", "label": "GPT-5.5 Mini"},
    {"id": "gpt-5.4", "label": "GPT-5.4"},
    {"id": "gpt-5.4-mini", "label": "GPT-5.4 Mini"},
    {"id": "gpt-5.4-nano", "label": "GPT-5.4 Nano"},
]

GEMINI_FALLBACK = [
    {"id": "gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro Preview"},
    {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash Preview"},
    {"id": "gemini-3.1-flash-lite-preview", "label": "Gemini 3.1 Flash Lite Preview"},
    {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
    {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
    {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite"},
]

CODEX_FALLBACK = [
    {"id": "gpt-5.5", "label": "GPT-5.5"},
    {"id": "gpt-5.5-mini", "label": "GPT-5.5 Mini"},
    {"id": "gpt-5.4", "label": "GPT-5.4"},
    {"id": "gpt-5.4-mini", "label": "GPT-5.4 Mini"},
    {"id": "gpt-5.3-codex", "label": "GPT-5.3 Codex"},
    {"id": "codex-mini-latest", "label": "Codex Mini Latest"},
]

_CODEX_LOGIN_PROCESS: subprocess.Popen | None = None
CODEX_LOGIN_LOG = Path.home() / ".sankalp" / "codex-login.log"


def provider_models(provider: str) -> dict[str, Any]:
    settings = load_settings(include_secrets=True)
    if provider == "local_openai":
        return _local_openai_models(settings)
    if provider == "openai":
        return _openai_models(settings)
    if provider == "gemini":
        return _gemini_models(settings)
    if provider == "codex":
        return _codex_models()
    return {"provider": provider, "models": [], "source": "none", "error": None}


def codex_status() -> dict[str, Any]:
    auth_path = Path.home() / ".codex" / "auth.json"
    logged_in = False
    auth_mode = ""
    if auth_path.exists():
        try:
            data = json.loads(auth_path.read_text(encoding="utf-8"))
            logged_in = bool(data.get("tokens") or data.get("OPENAI_API_KEY"))
            auth_mode = str(data.get("auth_mode") or "")
        except Exception:
            logged_in = False
    running = _CODEX_LOGIN_PROCESS is not None and _CODEX_LOGIN_PROCESS.poll() is None
    return {
        "logged_in": logged_in,
        "auth_mode": auth_mode,
        "login_running": running,
        "log_path": str(CODEX_LOGIN_LOG),
    }


def start_codex_login() -> dict[str, Any]:
    global _CODEX_LOGIN_PROCESS
    if _CODEX_LOGIN_PROCESS is not None and _CODEX_LOGIN_PROCESS.poll() is None:
        return {"ok": True, "already_running": True, "status": codex_status()}
    CODEX_LOGIN_LOG.parent.mkdir(parents=True, exist_ok=True)
    log = CODEX_LOGIN_LOG.open("a", encoding="utf-8")
    log.write(f"\n--- codex login {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log.flush()
    try:
        _CODEX_LOGIN_PROCESS = subprocess.Popen(["codex", "login"], stdout=log, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        log.write("Codex CLI was not found on PATH.\n")
        log.close()
        return {"ok": False, "error": "Codex CLI was not found on PATH.", "status": codex_status()}
    return {"ok": True, "already_running": False, "status": codex_status()}


def _openai_models(settings: dict[str, Any]) -> dict[str, Any]:
    api_key = settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"provider": "openai", "models": OPENAI_FALLBACK, "source": "fallback", "error": None}
    try:
        request = urllib.request.Request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        ids = sorted({item.get("id") for item in data.get("data", []) if _is_openai_chat_model(str(item.get("id") or ""))}, reverse=True)
        models = [{"id": model_id, "label": _label(model_id)} for model_id in ids[:40]]
        return {"provider": "openai", "models": models or OPENAI_FALLBACK, "source": "live", "error": None}
    except Exception as exc:
        return {"provider": "openai", "models": OPENAI_FALLBACK, "source": "fallback", "error": str(exc)}


def _local_openai_models(settings: dict[str, Any]) -> dict[str, Any]:
    base_url = str(settings.get("local_openai_base_url") or "").rstrip("/")
    configured = str(settings.get("local_openai_model") or "").strip()
    configured_models = [{"id": configured, "label": configured}] if configured else []
    if not base_url:
        return {"provider": "local_openai", "models": configured_models, "source": "configured", "error": None}
    headers = {"Content-Type": "application/json"}
    api_key = str(settings.get("local_openai_api_key") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        request = urllib.request.Request(f"{base_url}/models", headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
        ids = sorted({
            str(item.get("id") or "").strip()
            for item in data.get("data", [])
            if str(item.get("id") or "").strip()
        })
        models = [{"id": model_id, "label": _label(model_id)} for model_id in ids]
        if configured and not any(model["id"] == configured for model in models):
            models.insert(0, {"id": configured, "label": configured})
        return {"provider": "local_openai", "models": models or configured_models, "source": "live", "error": None}
    except Exception as exc:
        return {"provider": "local_openai", "models": configured_models, "source": "configured", "error": str(exc)}


def _gemini_models(settings: dict[str, Any]) -> dict[str, Any]:
    api_key = settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"provider": "gemini", "models": GEMINI_FALLBACK, "source": "fallback", "error": None}
    try:
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000&key={api_key}",
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        models = []
        for item in data.get("models", []):
            actions = item.get("supportedGenerationMethods") or item.get("supportedActions") or []
            model_id = str(item.get("name") or "").removeprefix("models/")
            if model_id and "generateContent" in actions and _is_gemini_chat_model(model_id):
                models.append({"id": model_id, "label": item.get("displayName") or _label(model_id)})
        models.sort(key=lambda item: item["id"], reverse=True)
        return {"provider": "gemini", "models": models or GEMINI_FALLBACK, "source": "live", "error": None}
    except Exception as exc:
        return {"provider": "gemini", "models": GEMINI_FALLBACK, "source": "fallback", "error": str(exc)}


def _codex_models() -> dict[str, Any]:
    if not codex_status()["logged_in"]:
        return {"provider": "codex", "models": CODEX_FALLBACK, "source": "fallback", "error": "not logged in"}
    try:
        proc = subprocess.run(["codex", "debug", "models"], text=True, capture_output=True, timeout=20)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "codex debug models failed")
        data = json.loads(proc.stdout)
        models = []
        for item in data.get("models", []):
            if item.get("visibility") == "list":
                slug = item["slug"]
                display_name = item.get("display_name")
                label = display_name if display_name and display_name != slug else _label(slug)
                models.append({"id": slug, "label": label})
        return {"provider": "codex", "models": models or CODEX_FALLBACK, "source": "codex", "error": None}
    except Exception as exc:
        return {"provider": "codex", "models": CODEX_FALLBACK, "source": "fallback", "error": str(exc)}


def _is_openai_chat_model(model_id: str) -> bool:
    return model_id.startswith(("gpt-", "o")) and not any(part in model_id for part in ["audio", "image", "tts", "transcribe", "realtime"])


def _is_gemini_chat_model(model_id: str) -> bool:
    blocked = ["image", "tts", "robotics", "embedding", "aqa", "learnlm", "veo", "imagen", "computer-use"]
    deprecated = {"gemini-3-pro-preview"}
    if model_id in deprecated:
        return False
    return model_id.startswith("gemini") and not any(part in model_id for part in blocked)


def _label(model_id: str) -> str:
    if model_id.startswith("gpt-"):
        return "GPT-" + model_id.removeprefix("gpt-").replace("-", " ").title()
    return model_id.replace("-", " ").replace("_", " ").title()
