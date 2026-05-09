from __future__ import annotations

import json
import mimetypes
import os
import platform
import shlex
import traceback
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from sankalp.agent import Agent
from sankalp.config import HOST, PORT, ROOT, SESSION_DIR, STATE_DIR, VAULT_DIR, ensure_dirs
from sankalp.macos import (
    APP_PATH as MACOS_APP_PATH,
    install_macos_app,
    macos_status,
    obsidian_status,
    open_full_disk_access,
    open_obsidian_download,
    request_vault_access,
)
from sankalp.memory import ObsidianMemory
from sankalp.provider_models import codex_status, provider_models, start_codex_login
from sankalp.sessions import SessionStore
from sankalp.settings import discover_obsidian_vaults, ensure_obsidian_vault_setting, load_settings, save_settings
from sankalp.skills import SkillRegistry, seed_builtin_skills
from sankalp.tools import ToolRegistry
from sankalp.updater import app_update_status, start_app_update


def build_agent() -> Agent:
    ensure_dirs()
    seed_builtin_skills()
    ensure_obsidian_vault_setting()
    settings = load_settings(include_secrets=True)
    vault = Path(str(settings.get("obsidian_vault_path") or VAULT_DIR)).expanduser()
    workspace = str(settings.get("obsidian_workspace_path") or "")
    memory = ObsidianMemory(vault, workspace=workspace)
    sessions = SessionStore(SESSION_DIR)
    tools = ToolRegistry(memory)
    return Agent(sessions, memory, tools)


AGENT = build_agent()
WEB_BUILD_DIR = ROOT / "web" / "build"
HTTPD: ThreadingHTTPServer | None = None


TOOLS = [
    {"name": "memory_remember", "description": "Save memory into the best matching Obsidian folder/note, creating it when needed."},
    {"name": "memory_search", "description": "Search the configured Obsidian vault (excluding session transcripts)."},
    {"name": "browser_fetch", "description": "Fetch and extract readable text from a URL."},
    {"name": "browser_search", "description": "Search the web and return top links for a topic."},
    {"name": "file_read", "description": "Read local files inside allowed roots."},
    {"name": "file_append", "description": "Append text to local files inside allowed roots."},
    {"name": "terminal", "description": "Run terminal commands when explicitly enabled by settings/env."},
    {"name": "computer_status", "description": "Report experimental macOS Computer Use availability and permission requirements."},
    {"name": "computer_list_apps", "description": "List visible macOS apps available to the Computer Use harness."},
    {"name": "computer_inspect", "description": "Inspect a macOS app accessibility tree for visible controls."},
    {"name": "computer_screenshot", "description": "Capture the current macOS screen for Computer Use observation."},
    {"name": "computer_open_app", "description": "Open or activate a macOS application."},
    {"name": "computer_open_permissions", "description": "Open macOS Privacy settings for Computer Use permissions."},
    {"name": "computer_click", "description": "Click an accessibility element path or screen coordinate."},
    {"name": "computer_type_text", "description": "Click an accessibility element and type text into it."},
    {"name": "computer_set_value", "description": "Set the value of an accessibility element when supported."},
    {"name": "computer_press_key", "description": "Press a keyboard key or key combination in an app."},
    {"name": "computer_scroll", "description": "Scroll an app using page or arrow key events."},
]

COMMANDS = [
    {"command": "/remember <fact>", "description": "Save a durable note in the best matching Obsidian folder or note."},
    {"command": "/fetch <url>", "description": "Fetch and summarize a webpage or text URL."},
    {"command": "/research <query>", "description": "Run web research search for the topic and list top sources."},
    {"command": "/read <path>", "description": "Read a local file from allowed roots."},
    {"command": "/append <path> :: <text>", "description": "Append text into a local file."},
    {"command": "/sh <command>", "description": "Run a terminal command when terminal access is enabled."},
    {"command": "/computer apps", "description": "List visible apps that Computer Use can currently see."},
    {"command": "/computer permissions [accessibility|screen]", "description": "Open macOS Privacy settings needed for Computer Use."},
    {"command": "/computer inspect <app>", "description": "Inspect one app and return visible accessibility element paths."},
    {"command": "/computer click <app> <path>", "description": "Click an inspected accessibility element path."},
    {"command": "/computer type <app> [path] :: <text>", "description": "Type text into the focused app or an inspected accessibility element."},
    {"command": "/computer task <instruction>", "description": "Run the experimental low-risk Computer Use loop."},
]


def capabilities_payload() -> dict[str, object]:
    return {
        "skills": SkillRegistry().capabilities(),
        "tools": TOOLS,
        "commands": COMMANDS,
    }


def reload_memory_from_settings() -> None:
    ensure_obsidian_vault_setting()
    settings = load_settings(include_secrets=True)
    vault = Path(str(settings.get("obsidian_vault_path") or VAULT_DIR)).expanduser()
    workspace = str(settings.get("obsidian_workspace_path") or "")
    memory = ObsidianMemory(vault, workspace=workspace)
    AGENT.memory = memory
    AGENT.tools = ToolRegistry(memory)


def resolve_web_asset(request_path: str, web_root: Path = WEB_BUILD_DIR) -> Path | None:
    if not web_root.exists():
        return None

    root = web_root.resolve()
    clean_path = unquote(request_path.split("?", 1)[0]).lstrip("/") or "index.html"
    candidate = (root / clean_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None

    if candidate.is_file():
        return candidate

    index = root / "index.html"
    if index.is_file():
        return index
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "Sankalp/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path != "/api" and not parsed.path.startswith("/api/"):
                asset = resolve_web_asset(parsed.path)
                if asset:
                    return self._file(asset)
                if parsed.path == "/":
                    return self._json({
                        "ok": True,
                        "name": "Sankalp",
                        "backend": f"http://{HOST}:{PORT}",
                        "webui": "Build the SvelteKit WebUI with `cd web && npm run build`.",
                    })
            if parsed.path == "/api/health":
                return self._json({"ok": True})
            if parsed.path == "/api/capabilities":
                return self._json({"capabilities": capabilities_payload()})
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
            if parsed.path == "/api/macos/obsidian-status":
                return self._json({"obsidian": obsidian_status()})
            if parsed.path == "/api/app/update":
                return self._json({"update": app_update_status()})
            if parsed.path == "/api/profile":
                return self._json({"profile": AGENT.memory.read_profile()})
            if parsed.path == "/api/settings":
                settings = ensure_obsidian_vault_setting()
                return self._json({"settings": settings})
            if parsed.path == "/api/models":
                query = parse_qs(parsed.query)
                provider = (query.get("provider") or [""])[0]
                return self._json({"models": provider_models(provider)})
            if parsed.path == "/api/codex/status":
                return self._json({"codex": codex_status()})
            return self._json({"error": "not found"}, status=404)
        except Exception:
            traceback.print_exc()
            return self._json({"error": "internal server error"}, status=500)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/chat":
                body = self._body()
                response = AGENT.turn(
                    body.get("session_id"),
                    body.get("message", ""),
                    {
                        "attachments": body.get("attachments") or [],
                        "options": body.get("options") or {},
                        "edit_index": body.get("edit_index"),
                    },
                )
                return self._json(response)
            if parsed.path == "/api/chat/stream":
                return self._chat_stream()
            if parsed.path == "/api/session/new":
                session = AGENT.sessions.create()
                return self._json({"session": session.compact(), "messages": [], "tool_calls": []})
            if parsed.path == "/api/session/rename":
                body = self._body()
                session = AGENT.sessions.rename(str(body.get("session_id") or ""), str(body.get("title") or ""))
                return self._json({"session": session.compact(), "sessions": AGENT.sessions.list()})
            if parsed.path == "/api/session/delete":
                body = self._body()
                session_id = str(body.get("session_id") or "")
                deleted = AGENT.sessions.delete(session_id)
                memory_deleted = AGENT.memory.delete_session_notes(session_id) if deleted else 0
                return self._json({"deleted": deleted, "memory_deleted": memory_deleted, "sessions": AGENT.sessions.list()})
            if parsed.path == "/api/session/truncate":
                body = self._body()
                session = AGENT.sessions.truncate_messages(
                    str(body.get("session_id") or ""),
                    int(body.get("index") or 0),
                )
                return self._json({
                    "session": session.compact(),
                    "messages": session.messages,
                    "tool_calls": session.tool_calls,
                })
            if parsed.path == "/api/settings":
                body = self._body()
                settings = save_settings(body)
                if "obsidian_vault_path" in body or "obsidian_workspace_path" in body:
                    reload_memory_from_settings()
                return self._json({"settings": settings, "memory_status": AGENT.memory.status()})
            if parsed.path == "/api/provider/test":
                return self._json({"test": AGENT.llm.test_provider(self._body())})
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
            if parsed.path == "/api/macos/open-obsidian-download":
                return self._json({"obsidian": open_obsidian_download()})
            if parsed.path == "/api/macos/request-vault-access":
                body = self._body()
                result = request_vault_access(str(body.get("default_path") or ""))
                if result.get("ok"):
                    settings = save_settings({"obsidian_vault_path": str(result["path"])})
                    reload_memory_from_settings()
                    return self._json({
                        "vault_access": result,
                        "settings": settings,
                        "memory_status": AGENT.memory.status(),
                    })
                return self._json({"vault_access": result, "memory_status": AGENT.memory.status()})
            if parsed.path == "/api/app/update":
                return self._json({"update": start_app_update()})
            if parsed.path == "/api/app/quit":
                _schedule_shutdown()
                return self._json({"ok": True, "message": "Sankalp is shutting down.", "close_tab": True})
            if parsed.path == "/api/app/restart":
                if not _schedule_restart():
                    return self._json({"ok": False, "error": "Restart is supported from the installed macOS or Windows app."}, status=400)
                return self._json({"ok": True, "message": "Sankalp is restarting.", "close_tab": True})
            if parsed.path == "/api/codex/login":
                return self._json({"codex": start_codex_login()})
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

    def _file(self, path: Path) -> None:
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(data)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _chat_stream(self) -> None:
        body = self._body()
        self.send_response(200)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("x-accel-buffering", "no")
        self.send_header("connection", "keep-alive")
        self.end_headers()

        def send(event: str, payload: object) -> None:
            data = json.dumps(payload)
            self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode("utf-8"))
            self.wfile.flush()

        try:
            for item in AGENT.turn_stream(
                body.get("session_id"),
                body.get("message", ""),
                {
                    "attachments": body.get("attachments") or [],
                    "options": body.get("options") or {},
                    "edit_index": body.get("edit_index"),
                },
            ):
                send(str(item.get("event") or "status"), item.get("data") or {})
            self.close_connection = True
        except Exception as exc:
            traceback.print_exc()
            send("error", {"error": str(exc)})
            self.close_connection = True

def main() -> None:
    global HTTPD
    ensure_dirs()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    HTTPD = httpd
    print(f"Sankalp listening on http://{HOST}:{PORT}", flush=True)
    print(f"Obsidian memory vault: {VAULT_DIR}", flush=True)
    httpd.serve_forever()


def _schedule_shutdown() -> None:
    if HTTPD is None:
        return

    def _shutdown() -> None:
        # Reply is sent before shutdown starts, then stop accepting new requests.
        time.sleep(0.2)
        HTTPD.shutdown()
        HTTPD.server_close()

    threading.Thread(target=_shutdown, daemon=True).start()


def _schedule_restart() -> bool:
    if not _schedule_relaunch():
        return False
    _schedule_shutdown()
    return True


def _schedule_relaunch() -> bool:
    system = platform.system()
    if system == "Darwin":
        app_path = Path(os.environ.get("SANKALP_APP_PATH", str(MACOS_APP_PATH))).expanduser()
        command = f"sleep 1; /usr/bin/open {shlex.quote(str(app_path))}"
        subprocess.Popen(["/bin/sh", "-c", command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    if system == "Windows":
        launcher = STATE_DIR / "bin" / "sankalp.cmd"
        launcher_arg = str(launcher).replace("'", "''")
        command = f"Start-Sleep -Milliseconds 1000; Start-Process -FilePath '{launcher_arg}'"
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-Command", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        )
        return True
    return False
