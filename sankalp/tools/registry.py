from __future__ import annotations

import fnmatch
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from sankalp.computer import MacOSComputerUse
from sankalp.config import ALLOW_TERMINAL
from sankalp.memory import ObsidianMemory
from sankalp.settings import allowed_roots_from_settings, load_settings

from .base import ToolResult
from .web_research import WebResearchClient


class ToolRegistry:
    def __init__(self, memory: ObsidianMemory):
        self.memory = memory
        self.roots = allowed_roots_from_settings()
        self.computer = MacOSComputerUse()

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        if name == "memory_remember":
            return self.memory_remember(**kwargs)
        if name == "memory_search":
            return self.memory_search(**kwargs)
        if name == "browser_fetch":
            return self.browser_fetch(**kwargs)
        if name == "browser_search":
            return self.browser_search(**kwargs)
        if name == "file_read":
            return self.file_read(**kwargs)
        if name == "file_list":
            return self.file_list(**kwargs)
        if name == "file_find":
            return self.file_find(**kwargs)
        if name == "file_append":
            return self.file_append(**kwargs)
        if name == "terminal":
            return self.terminal(**kwargs)
        if name == "computer_status":
            return self.computer_status(**kwargs)
        if name == "computer_list_apps":
            return self.computer_list_apps(**kwargs)
        if name == "computer_open_app":
            return self.computer_open_app(**kwargs)
        if name == "computer_open_permissions":
            return self.computer_open_permissions(**kwargs)
        if name == "computer_inspect":
            return self.computer_inspect(**kwargs)
        if name == "computer_screenshot":
            return self.computer_screenshot(**kwargs)
        if name == "computer_click":
            return self.computer_click(**kwargs)
        if name == "computer_type_text":
            return self.computer_type_text(**kwargs)
        if name == "computer_set_value":
            return self.computer_set_value(**kwargs)
        if name == "computer_press_key":
            return self.computer_press_key(**kwargs)
        if name == "computer_scroll":
            return self.computer_scroll(**kwargs)
        if name == "computer_wait":
            return self.computer_wait(**kwargs)
        return ToolResult.run(name, kwargs, {"error": f"unknown tool: {name}"}, status="error")

    def memory_remember(self, text: str, source: str = "chat", folder: str | None = None, note: str | None = None) -> ToolResult:
        started = time.time()
        target = self.memory.remember_target(text, folder=folder, note=note)
        path = self.memory.capture(text, source=source, folder=folder, note=note)
        output = {"path": str(path), "target": target}
        return ToolResult.run(
            "memory_remember",
            {"text": text, "source": source, "folder": folder, "note": note},
            output,
            started_at=started,
        )

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
            result = WebResearchClient(load_settings(include_secrets=True)).fetch(url)
            return ToolResult.run("browser_fetch", {"url": url}, result, started_at=started)
        except Exception as exc:
            return ToolResult.run("browser_fetch", {"url": url}, {"error": str(exc)}, "error", started)

    def browser_search(self, query: str, limit: int = 5, include_content: bool = True) -> ToolResult:
        started = time.time()
        q = (query or "").strip()
        if not q:
            return ToolResult.run("browser_search", {"query": query, "limit": limit}, {"error": "query is empty"}, "error", started)
        limit = max(1, min(int(limit or 5), 10))
        try:
            output = WebResearchClient(load_settings(include_secrets=True)).search(q, limit=limit, include_content=include_content)
            status = "ok" if output.get("results") else "error"
            return ToolResult.run(
                "browser_search",
                {"query": q, "limit": limit, "include_content": include_content},
                output,
                status=status,
                started_at=started,
            )
        except Exception as exc:
            return ToolResult.run("browser_search", {"query": q, "limit": limit}, {"error": str(exc)}, "error", started)

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

    def file_list(self, path: str = ".", limit: int = 100, include_hidden: bool = False) -> ToolResult:
        started = time.time()
        resolved = self._resolve_allowed(path or ".")
        if resolved is None:
            return ToolResult.run("file_list", {"path": path}, {"error": "path is outside allowed roots"}, "blocked", started)
        if not resolved.exists():
            return ToolResult.run("file_list", {"path": path}, {"error": "path does not exist", "resolved": str(resolved)}, "error", started)
        if not resolved.is_dir():
            return ToolResult.run("file_list", {"path": path}, {"error": "path is not a directory", "resolved": str(resolved)}, "error", started)
        try:
            limit = max(1, min(int(limit or 100), 300))
            entries = []
            for item in sorted(resolved.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.lower())):
                if not include_hidden and item.name.startswith("."):
                    continue
                entries.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "directory" if item.is_dir() else "file",
                })
                if len(entries) >= limit:
                    break
            return ToolResult.run(
                "file_list",
                {"path": path, "limit": limit, "include_hidden": include_hidden},
                {
                    "path": str(resolved),
                    "entries": entries,
                    "truncated": len(entries) >= limit,
                    "allowed_roots": [str(root) for root in self.roots],
                },
                started_at=started,
            )
        except Exception as exc:
            return ToolResult.run("file_list", {"path": path}, {"error": str(exc), "resolved": str(resolved)}, "error", started)

    def file_find(
        self,
        query: str,
        path: str = "",
        kind: str = "any",
        limit: int = 80,
        max_depth: int = 8,
        include_hidden: bool = False,
    ) -> ToolResult:
        started = time.time()
        needle = (query or "").strip()
        if not needle:
            return ToolResult.run("file_find", {"query": query}, {"error": "query is empty"}, "error", started)
        roots = self._find_roots(path)
        if not roots:
            return ToolResult.run("file_find", {"query": query, "path": path}, {"error": "path is outside allowed roots"}, "blocked", started)
        limit = max(1, min(int(limit or 80), 300))
        max_depth = max(0, min(int(max_depth or 8), 20))
        matches: list[dict[str, str]] = []
        visited = 0
        pattern = needle.lower()
        wildcard = any(char in pattern for char in "*?[]")
        for root in roots:
            for current, dirnames, filenames in os.walk(root):
                current_path = Path(current)
                try:
                    depth = len(current_path.relative_to(root).parts)
                except ValueError:
                    depth = 0
                if depth >= max_depth:
                    dirnames[:] = []
                if not include_hidden:
                    dirnames[:] = [name for name in dirnames if not name.startswith(".")]
                    filenames = [name for name in filenames if not name.startswith(".")]
                names = []
                if kind in {"any", "directory", "folder", "dir"}:
                    names.extend((name, "directory") for name in dirnames)
                if kind in {"any", "file"}:
                    names.extend((name, "file") for name in filenames)
                for name, item_type in sorted(names, key=lambda item: item[0].lower()):
                    visited += 1
                    lower = name.lower()
                    if (wildcard and fnmatch.fnmatch(lower, pattern)) or (not wildcard and pattern in lower):
                        matches.append({"name": name, "path": str(current_path / name), "type": item_type})
                        if len(matches) >= limit:
                            return ToolResult.run(
                                "file_find",
                                {"query": needle, "path": path, "kind": kind, "limit": limit, "max_depth": max_depth},
                                {
                                    "matches": matches,
                                    "truncated": True,
                                    "searched_roots": [str(item) for item in roots],
                                    "visited": visited,
                                },
                                started_at=started,
                            )
        return ToolResult.run(
            "file_find",
            {"query": needle, "path": path, "kind": kind, "limit": limit, "max_depth": max_depth},
            {
                "matches": matches,
                "truncated": False,
                "searched_roots": [str(item) for item in roots],
                "visited": visited,
            },
            started_at=started,
        )

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
            self._refresh_roots()
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

    def computer_status(self) -> ToolResult:
        started = time.time()
        return ToolResult.run("computer_status", {}, self.computer.status(), started_at=started)

    def computer_list_apps(self) -> ToolResult:
        started = time.time()
        output = self.computer.list_apps()
        status = "ok" if not output.get("error") else "error"
        return ToolResult.run("computer_list_apps", {}, output, status, started)

    def computer_open_app(self, app: str) -> ToolResult:
        started = time.time()
        output = self.computer.open_app(app)
        status = "ok" if output.get("ok") else "error"
        return ToolResult.run("computer_open_app", {"app": app}, output, status, started)

    def computer_open_permissions(self, target: str = "accessibility") -> ToolResult:
        started = time.time()
        output = self.computer.open_permissions(target)
        status = "ok" if output.get("ok") else "error"
        return ToolResult.run("computer_open_permissions", {"target": target}, output, status, started)

    def computer_inspect(self, app: str, max_depth: int = 3, max_children: int = 45) -> ToolResult:
        started = time.time()
        output = self.computer.inspect_app(app, max_depth=max_depth, max_children=max_children)
        status = "ok" if not output.get("error") else "error"
        return ToolResult.run(
            "computer_inspect",
            {"app": app, "max_depth": max_depth, "max_children": max_children},
            output,
            status,
            started,
        )

    def computer_screenshot(self) -> ToolResult:
        started = time.time()
        output = self.computer.screenshot()
        status = "ok" if output.get("ok") else "error"
        return ToolResult.run("computer_screenshot", {}, output, status, started)

    def computer_click(self, app: str = "", element_path: str = "", x: int | None = None, y: int | None = None) -> ToolResult:
        started = time.time()
        output = self.computer.click(app=app, element_path=element_path, x=x, y=y)
        status = "ok" if output.get("ok") else "error"
        return ToolResult.run(
            "computer_click",
            {"app": app, "element_path": element_path, "x": x, "y": y},
            output,
            status,
            started,
        )

    def computer_type_text(self, app: str, element_path: str, text: str) -> ToolResult:
        started = time.time()
        output = self.computer.type_text(app, element_path, text)
        status = "ok" if output.get("ok") else "error"
        return ToolResult.run(
            "computer_type_text",
            {"app": app, "element_path": element_path, "chars": len(text)},
            output,
            status,
            started,
        )

    def computer_set_value(self, app: str, element_path: str, value: str) -> ToolResult:
        started = time.time()
        output = self.computer.set_value(app, element_path, value)
        status = "ok" if output.get("ok") else "error"
        return ToolResult.run(
            "computer_set_value",
            {"app": app, "element_path": element_path, "chars": len(value)},
            output,
            status,
            started,
        )

    def computer_press_key(self, app: str, key: str) -> ToolResult:
        started = time.time()
        output = self.computer.press_key(app, key)
        status = "ok" if output.get("ok") else "error"
        return ToolResult.run("computer_press_key", {"app": app, "key": key}, output, status, started)

    def computer_scroll(self, app: str, direction: str = "down", pages: int = 1) -> ToolResult:
        started = time.time()
        output = self.computer.scroll(app, direction=direction, pages=pages)
        status = "ok" if output.get("ok") else "error"
        return ToolResult.run(
            "computer_scroll",
            {"app": app, "direction": direction, "pages": pages},
            output,
            status,
            started,
        )

    def computer_wait(self, seconds: float = 1.0) -> ToolResult:
        started = time.time()
        output = self.computer.wait(seconds)
        return ToolResult.run("computer_wait", {"seconds": seconds}, output, started_at=started)

    def _resolve_allowed(self, path: str) -> Path | None:
        self._refresh_roots()
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

    def _find_roots(self, path: str = "") -> list[Path]:
        self._refresh_roots()
        if not path:
            return [root for root in self.roots if root.exists() and root.is_dir()]
        resolved = self._resolve_allowed(path)
        if resolved is None or not resolved.exists() or not resolved.is_dir():
            return []
        return [resolved]

    def _refresh_roots(self) -> None:
        self.roots = allowed_roots_from_settings()
