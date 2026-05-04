from __future__ import annotations

import html
import shlex
import subprocess
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from sankalp.config import ALLOW_TERMINAL, allowed_roots
from sankalp.memory import ObsidianMemory

from .base import ToolResult


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return html.unescape("\n".join(self.parts))


class ToolRegistry:
    def __init__(self, memory: ObsidianMemory):
        self.memory = memory
        self.roots = allowed_roots()

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        if name == "memory_remember":
            return self.memory_remember(**kwargs)
        if name == "memory_search":
            return self.memory_search(**kwargs)
        if name == "browser_fetch":
            return self.browser_fetch(**kwargs)
        if name == "file_read":
            return self.file_read(**kwargs)
        if name == "file_append":
            return self.file_append(**kwargs)
        if name == "terminal":
            return self.terminal(**kwargs)
        return ToolResult.run(name, kwargs, {"error": f"unknown tool: {name}"}, status="error")

    def memory_remember(self, text: str, source: str = "chat") -> ToolResult:
        started = time.time()
        path = self.memory.capture(text, source=source)
        return ToolResult.run("memory_remember", {"text": text, "source": source}, {"path": str(path)}, started_at=started)

    def memory_search(self, query: str, limit: int = 6, original_query: str | None = None) -> ToolResult:
        started = time.time()
        hits = self.memory.retrieve(query, limit=limit)
        return ToolResult.run(
            "memory_search",
            {"query": query, "original_query": original_query or query, "limit": limit},
            {
                "status": self.memory.status(),
                "hits": [hit.__dict__ for hit in hits],
            },
            started_at=started,
        )

    def browser_fetch(self, url: str) -> ToolResult:
        started = time.time()
        if not url.startswith(("http://", "https://")):
            return ToolResult.run("browser_fetch", {"url": url}, {"error": "URL must start with http:// or https://"}, "error", started)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Sankalp/0.1"})
            with urllib.request.urlopen(request, timeout=12) as response:
                body = response.read(1_000_000)
                content_type = response.headers.get("content-type", "")
            raw = body.decode("utf-8", errors="replace")
            if "html" in content_type.lower():
                parser = TextExtractor()
                parser.feed(raw)
                text = parser.text()
            else:
                text = raw
            return ToolResult.run("browser_fetch", {"url": url}, {"content_type": content_type, "text": text[:12000]}, started_at=started)
        except Exception as exc:
            return ToolResult.run("browser_fetch", {"url": url}, {"error": str(exc)}, "error", started)

    def file_read(self, path: str) -> ToolResult:
        started = time.time()
        resolved = self._resolve_allowed(path)
        if resolved is None:
            return ToolResult.run("file_read", {"path": path}, {"error": "path is outside allowed roots"}, "blocked", started)
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
            return ToolResult.run("file_read", {"path": path}, {"path": str(resolved), "text": text[:20000]}, started_at=started)
        except Exception as exc:
            return ToolResult.run("file_read", {"path": path}, {"error": str(exc)}, "error", started)

    def file_append(self, path: str, text: str) -> ToolResult:
        started = time.time()
        resolved = self._resolve_allowed(path)
        if resolved is None:
            return ToolResult.run("file_append", {"path": path}, {"error": "path is outside allowed roots"}, "blocked", started)
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with resolved.open("a", encoding="utf-8") as handle:
                handle.write(text)
            return ToolResult.run("file_append", {"path": path, "bytes": len(text.encode("utf-8"))}, {"path": str(resolved)}, started_at=started)
        except Exception as exc:
            return ToolResult.run("file_append", {"path": path}, {"error": str(exc)}, "error", started)

    def terminal(self, command: str) -> ToolResult:
        started = time.time()
        if not ALLOW_TERMINAL:
            return ToolResult.run("terminal", {"command": command}, {"error": "terminal disabled; set SANKALP_ALLOW_TERMINAL=1"}, "blocked", started)
        try:
            argv = shlex.split(command)
            if not argv:
                return ToolResult.run("terminal", {"command": command}, {"error": "empty command"}, "error", started)
            proc = subprocess.run(argv, cwd=str(self.roots[0]), text=True, capture_output=True, timeout=30)
            return ToolResult.run(
                "terminal",
                {"command": command},
                {"returncode": proc.returncode, "stdout": proc.stdout[-12000:], "stderr": proc.stderr[-12000:]},
                "ok" if proc.returncode == 0 else "error",
                started,
            )
        except Exception as exc:
            return ToolResult.run("terminal", {"command": command}, {"error": str(exc)}, "error", started)

    def _resolve_allowed(self, path: str) -> Path | None:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.roots[0] / candidate
        try:
            resolved = candidate.resolve()
        except FileNotFoundError:
            resolved = candidate.parent.resolve() / candidate.name
        for root in self.roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        return None
