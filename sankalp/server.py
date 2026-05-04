from __future__ import annotations

import json
import mimetypes
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from sankalp.agent import Agent
from sankalp.config import HOST, PORT, ROOT, SESSION_DIR, VAULT_DIR, ensure_dirs
from sankalp.memory import ObsidianMemory
from sankalp.sessions import SessionStore
from sankalp.settings import load_settings, save_settings
from sankalp.tools import ToolRegistry


STATIC_DIR = ROOT / "sankalp" / "static"


def build_agent() -> Agent:
    ensure_dirs()
    memory = ObsidianMemory(VAULT_DIR)
    sessions = SessionStore(SESSION_DIR)
    tools = ToolRegistry(memory)
    return Agent(sessions, memory, tools)


AGENT = build_agent()


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
                return self._json({"memory": AGENT.memory.list_recent(limit=50)})
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
                return self._json({"settings": save_settings(body)})
            if parsed.path == "/api/profile":
                body = self._body()
                AGENT.memory.save_self_profile(str(body.get("self_profile") or ""))
                return self._json({"profile": AGENT.memory.read_profile()})
            if parsed.path == "/api/profile/trait/delete":
                body = self._body()
                deleted = AGENT.memory.delete_trait(str(body.get("trait_id") or ""))
                return self._json({"deleted": deleted, "profile": AGENT.memory.read_profile()})
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
