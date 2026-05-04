from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST = os.environ.get("SANKALP_HOST", "127.0.0.1")
PORT = int(os.environ.get("SANKALP_PORT", "8765"))
STATE_DIR = Path(os.environ.get("SANKALP_STATE_DIR", "~/.sankalp")).expanduser()
SESSION_DIR = STATE_DIR / "sessions"
VAULT_DIR = Path(os.environ.get("SANKALP_OBSIDIAN_VAULT", str(STATE_DIR / "obsidian-vault"))).expanduser()
MODEL = os.environ.get("SANKALP_MODEL", "gpt-5.5")
ALLOW_TERMINAL = os.environ.get("SANKALP_ALLOW_TERMINAL", "").lower() in {"1", "true", "yes"}


def allowed_roots() -> list[Path]:
    configured = os.environ.get("SANKALP_ALLOWED_ROOTS")
    if configured:
        roots = [Path(part).expanduser().resolve() for part in configured.split(os.pathsep) if part.strip()]
    else:
        roots = [ROOT.resolve(), VAULT_DIR.resolve()]
    return roots


def ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
