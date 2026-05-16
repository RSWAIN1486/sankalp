from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST = os.environ.get("SANKALP_HOST", "127.0.0.1")
PORT = int(os.environ.get("SANKALP_PORT", "8765"))
STATE_DIR = Path(os.environ.get("SANKALP_STATE_DIR", "~/.sankalp")).expanduser()
APP_DIR = STATE_DIR / "app"
BACKEND_DIR = APP_DIR / "sankalp"
FRONTEND_DIR = APP_DIR / "web"
SESSION_DIR = STATE_DIR / "sessions"
SKILLS_DIR = STATE_DIR / "skills"
HOOKS_DIR = STATE_DIR / "hooks"
GATEWAY_DIR = STATE_DIR / "gateway"
LOGS_DIR = STATE_DIR / "logs"
CACHE_DIR = STATE_DIR / "cache"
SANDBOXES_DIR = STATE_DIR / "sandboxes"
MEMORIES_DIR = STATE_DIR / "memories"
WEBUI_DIR = STATE_DIR / "webui"
TOOLS_DIR = STATE_DIR / "tools"
SOUL_FILE = STATE_DIR / "SOUL.md"
STATE_DB = STATE_DIR / "state.db"
VAULT_DIR = Path(os.environ.get("SANKALP_OBSIDIAN_VAULT", str(STATE_DIR / "obsidian-vault"))).expanduser()
MODEL = os.environ.get("SANKALP_MODEL", "gpt-5.5")
ALLOW_TERMINAL = os.environ.get("SANKALP_ALLOW_TERMINAL", "").lower() in {"1", "true", "yes"}

DEFAULT_SOUL = """# Sankalp Agent Persona

<!--
This file defines Sankalp's local agent personality and tone.
Edit it to customize how Sankalp communicates with you.

Delete the contents to use the default personality.
-->
"""


def allowed_roots() -> list[Path]:
    configured = os.environ.get("SANKALP_ALLOWED_ROOTS")
    if configured:
        roots = [Path(part).expanduser().resolve() for part in configured.split(os.pathsep) if part.strip()]
    else:
        roots = [ROOT.resolve(), VAULT_DIR.resolve()]
    return roots


def ensure_dirs() -> None:
    for directory in [
        STATE_DIR,
        SESSION_DIR,
        SKILLS_DIR,
        HOOKS_DIR,
        GATEWAY_DIR,
        LOGS_DIR,
        CACHE_DIR,
        SANDBOXES_DIR,
        MEMORIES_DIR,
        WEBUI_DIR,
        TOOLS_DIR,
        VAULT_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    if not SOUL_FILE.exists():
        SOUL_FILE.write_text(DEFAULT_SOUL, encoding="utf-8")
