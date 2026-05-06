from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from sankalp import __version__
from sankalp.config import HOST, PORT, ROOT


DEFAULT_UPDATE_URL = "https://raw.githubusercontent.com/RSWAIN1486/sankalp/main/update.json"
DEFAULT_REPO_URL = "https://github.com/RSWAIN1486/sankalp.git"


def app_update_status(force: bool = False) -> dict[str, Any]:
    local = _local_manifest()
    status: dict[str, Any] = {
        "ok": True,
        "current_version": str(local.get("version") or __version__),
        "current_commit": _git(["rev-parse", "--short", "HEAD"]),
        "repo_root": str(ROOT),
        "manifest_url": os.environ.get("SANKALP_UPDATE_URL", DEFAULT_UPDATE_URL),
        "checked_at": int(time.time()),
        "update_available": False,
    }

    try:
        remote = fetch_update_manifest()
    except Exception as exc:
        status.update({"ok": False, "error": str(exc)})
        return status

    latest_version = str(remote.get("version") or "")
    status.update({
        "latest": remote,
        "latest_version": latest_version,
        "update_available": _is_newer_version(latest_version, status["current_version"]),
    })
    if force:
        status["forced"] = True
    return status


def fetch_update_manifest() -> dict[str, Any]:
    url = os.environ.get("SANKALP_UPDATE_URL", DEFAULT_UPDATE_URL)
    request = urllib.request.Request(url, headers={"User-Agent": "Sankalp/0.1"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def start_app_update() -> dict[str, Any]:
    system = platform.system()
    if system == "Darwin":
        script = ROOT / "scripts" / "install_macos.sh"
    elif system == "Windows":
        script = ROOT / "scripts" / "install_windows.ps1"
    else:
        return {"ok": False, "error": f"In-app updates are not yet supported on {system}."}
    if not script.exists():
        return {"ok": False, "error": f"Installer script not found at {script}"}

    env = os.environ.copy()
    env.update({
        "SANKALP_REPO_URL": env.get("SANKALP_REPO_URL", DEFAULT_REPO_URL),
        "SANKALP_BRANCH": env.get("SANKALP_BRANCH", "main"),
        "SANKALP_HOST": env.get("SANKALP_HOST", HOST),
        "SANKALP_PORT": env.get("SANKALP_PORT", str(PORT)),
        "SANKALP_OPEN_AFTER_INSTALL": "1",
    })

    threading.Thread(target=_run_update, args=(script, env, system), daemon=True).start()
    return {
        "ok": True,
        "message": "Update started. Sankalp will rebuild, reinstall, and reopen when ready.",
        "repo_root": str(ROOT),
    }


def _run_update(script: Path, env: dict[str, str], system: str) -> None:
    time.sleep(0.5)
    if system == "Darwin":
        tmp_dir = Path(tempfile.mkdtemp(prefix="sankalp-update-"))
        runnable = tmp_dir / "install_macos.sh"
        shutil.copy2(script, runnable)
        subprocess.Popen(
            ["/bin/bash", str(runnable)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return
    if system == "Windows":
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        )


def _local_manifest() -> dict[str, Any]:
    path = ROOT / "update.json"
    if not path.exists():
        return {"version": __version__}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": __version__}


def _git(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            text=True,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _is_newer_version(latest: str, current: str) -> bool:
    latest_parts = _version_parts(latest)
    current_parts = _version_parts(current)
    return latest_parts > current_parts


def _version_parts(version: str) -> tuple[int, int, int, str]:
    pieces = version.strip().lstrip("v").split(".", 2)
    numbers: list[int] = []
    suffix = ""
    for piece in pieces:
        digits = ""
        rest = ""
        for char in piece:
            if char.isdigit() and not rest:
                digits += char
            else:
                rest += char
        numbers.append(int(digits or "0"))
        if rest:
            suffix = rest
    while len(numbers) < 3:
        numbers.append(0)
    return numbers[0], numbers[1], numbers[2], suffix
