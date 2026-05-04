from __future__ import annotations

import json
import mimetypes
import traceback
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sankalp.agent import Agent
from sankalp.config import HOST, PORT, ROOT, SESSION_DIR, VAULT_DIR, ensure_dirs
from sankalp.macos import install_macos_app, macos_status, open_full_disk_access, relaunch_with_latest_code
from sankalp.memory import ObsidianMemory
from sankalp.sessions import SessionStore
from sankalp.settings import discover_obsidian_vaults, load_settings, save_settings
from sankalp.tools import ToolRegistry


STATIC_DIR = ROOT / "sankalp" / "static"


def build_agent() -> Agent:
    ensure_dirs()
    settings = load_settings(include_secrets=True)
    vault = Path(str(settings.get("obsidian_vault_path") or VAULT_DIR)).expanduser()
    workspace = str(settings.get("obsidian_workspace_path") or "")
    memory = ObsidianMemory(vault, workspace=workspace)
    sessions = SessionStore(SESSION_DIR)
    tools = ToolRegistry(memory)
    return Agent(sessions, memory, tools)


AGENT = build_agent()


def reload_memory_from_settings() -> None:
    settings = load_settings(include_secrets=True)
    vault = Path(str(settings.get("obsidian_vault_path") or VAULT_DIR)).expanduser()
    workspace = str(settings.get("obsidian_workspace_path") or "")
    memory = ObsidianMemory(vault, workspace=workspace)
    AGENT.memory = memory
    AGENT.tools = ToolRegistry(memory)


class Handler(BaseHTTPRequestHandler):
    server_version = "Sankalp/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self._static("index.html")
            if parsed.path.startswith("/static/"):
                return self._static(parsed.path.removeprefix("/static/"))
            if parsed.path == "/api/health":
                return self._json({"ok": True})
            if parsed.path == "/api/sessions":
                return self._json({"sessions": AGENT.sessions.list()})
            if parsed.path == "/api/session":
                query = parse_qs(parsed.query)
                session = AGENT.sessions.get((query.get("id") or [None])[0])
                return self._json({
                    "session": session.compact(),
                    "messages": session.messages,
                    "tool_calls": session.tool_calls,
                })
            if parsed.path == "/api/memory":
                return self._json({"memory": AGENT.memory.list_recent(limit=50), "status": AGENT.memory.status()})
            if parsed.path == "/api/memory/tree":
                return self._json({"tree": AGENT.memory.tree(), "status": AGENT.memory.status()})
            if parsed.path == "/api/memory/folders":
                return self._json({"folders": AGENT.memory.folders(), "status": AGENT.memory.status()})
            if parsed.path == "/api/memory/children":
                query = parse_qs(parsed.query)
                folder = (query.get("folder") or [""])[0]
                return self._json({"children": AGENT.memory.children(folder), "status": AGENT.memory.status()})
            if parsed.path == "/api/memory/notes":
                query = parse_qs(parsed.query)
                folder = (query.get("folder") or [""])[0]
                return self._json({"notes": AGENT.memory.notes(folder), "status": AGENT.memory.status()})
            if parsed.path == "/api/obsidian/vaults":
                return self._json({"vaults": discover_obsidian_vaults()})
            if parsed.path == "/api/macos/status":
                return self._json({"macos": macos_status()})
            if parsed.path == "/api/profile":
                return self._json({"profile": AGENT.memory.read_profile()})
            if parsed.path == "/api/settings":
                return self._json({"settings": load_settings()})
            return self._json({"error": "not found"}, status=404)
        except Exception:
            traceback.print_exc()
            return self._json({"error": "internal server error"}, status=500)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/chat":
                body = self._body()
                response = AGENT.turn(body.get("session_id"), body.get("message", ""))
                return self._json(response)
            if parsed.path == "/api/session/new":
                session = AGENT.sessions.create()
                return self._json({"session": session.compact(), "messages": [], "tool_calls": []})
            if parsed.path == "/api/settings":
                body = self._body()
                settings = save_settings(body)
                if "obsidian_vault_path" in body or "obsidian_workspace_path" in body:
                    reload_memory_from_settings()
                return self._json({"settings": settings, "memory_status": AGENT.memory.status()})
            if parsed.path == "/api/profile":
                body = self._body()
                AGENT.memory.save_self_profile(str(body.get("self_profile") or ""))
                return self._json({"profile": AGENT.memory.read_profile()})
            if parsed.path == "/api/profile/trait/delete":
                body = self._body()
                deleted = AGENT.memory.delete_trait(str(body.get("trait_id") or ""))
                return self._json({"deleted": deleted, "profile": AGENT.memory.read_profile()})
            if parsed.path == "/api/macos/install-app":
                return self._json({"macos": install_macos_app()})
            if parsed.path == "/api/macos/open-full-disk-access":
                return self._json({"macos": open_full_disk_access()})
            if parsed.path == "/api/app/relaunch":
                return self._json({"relaunch": relaunch_with_latest_code()})
            if parsed.path == "/api/memory/open":
                body = self._body()
                result = AGENT.memory.open_target(str(body.get("path") or ""))
                if result.get("ok"):
                    if result.get("mode") == "obsidian":
                        subprocess.Popen(["open", str(result["uri"])])
                    elif result.get("mode") == "finder":
                        subprocess.Popen(["open", str(result["path"])])
                return self._json({"open": result})
            return self._json({"error": "not found"}, status=404)
        except Exception:
            traceback.print_exc()
            return self._json({"error": "internal server error"}, status=500)

    def _body(self) -> dict[str, object]:
        length = int(self.headers.get("content-length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, payload: object, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _static(self, relative: str) -> None:
        path = (STATIC_DIR / relative).resolve()
        try:
            path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            return self._json({"error": "not found"}, status=404)
        if not path.exists() or not path.is_file():
            return self._json({"error": "not found"}, status=404)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    ensure_dirs()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Sankalp listening on http://{HOST}:{PORT}", flush=True)
    print(f"Obsidian memory vault: {VAULT_DIR}", flush=True)
    httpd.serve_forever()
