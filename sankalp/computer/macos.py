from __future__ import annotations

import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from sankalp.config import CACHE_DIR, TOOLS_DIR


ACCESSIBILITY_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
SCREEN_RECORDING_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
_CLICK_HELPER_SOURCE = r"""
#include <ApplicationServices/ApplicationServices.h>
#include <CoreGraphics/CoreGraphics.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static void post_mouse(CGEventType type, CGPoint point, CGMouseButton button) {
  CGEventRef event = CGEventCreateMouseEvent(NULL, type, point, button);
  if (!event) {
    exit(3);
  }
  CGEventPost(kCGHIDEventTap, event);
  CFRelease(event);
}

int main(int argc, char **argv) {
  if (argc < 3) {
    fprintf(stderr, "usage: sankalp-click <screenshot-x> <screenshot-y>\n");
    return 2;
  }

  double input_x = atof(argv[1]);
  double input_y = atof(argv[2]);
  CGDirectDisplayID display = CGMainDisplayID();
  CGRect bounds = CGDisplayBounds(display);
  size_t pixels_w = CGDisplayPixelsWide(display);
  size_t pixels_h = CGDisplayPixelsHigh(display);
  if (pixels_w == 0 || pixels_h == 0 || bounds.size.width <= 0 || bounds.size.height <= 0) {
    fprintf(stderr, "could not read display geometry\n");
    return 4;
  }

  double scaled_x = bounds.origin.x + (input_x * bounds.size.width / (double)pixels_w);
  double scaled_y = bounds.origin.y + (input_y * bounds.size.height / (double)pixels_h);
  CGPoint point = CGPointMake(scaled_x, scaled_y);

  post_mouse(kCGEventMouseMoved, point, kCGMouseButtonLeft);
  usleep(50000);
  post_mouse(kCGEventLeftMouseDown, point, kCGMouseButtonLeft);
  usleep(80000);
  post_mouse(kCGEventLeftMouseUp, point, kCGMouseButtonLeft);

  printf("input_x=%.0f input_y=%.0f click_x=%.2f click_y=%.2f pixels_w=%zu pixels_h=%zu bounds_w=%.2f bounds_h=%.2f\n",
         input_x, input_y, scaled_x, scaled_y, pixels_w, pixels_h, bounds.size.width, bounds.size.height);
  return 0;
}
"""


class MacOSComputerUse:
    """macOS desktop observation and low-level UI actions via built-in tools."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or CACHE_DIR / "computer-use"

    def status(self) -> dict[str, Any]:
        osascript = shutil.which("osascript")
        screencapture = shutil.which("screencapture")
        return {
            "is_macos": self._is_macos(),
            "backend": "macos-osascript",
            "available": self._is_macos() and bool(osascript),
            "tools": {
                "osascript": osascript or "",
                "screencapture": screencapture or "",
            },
            "permissions": {
                "accessibility": "required for app inspection and clicks",
                "screen_recording": "required for screenshots",
                "dev_mode_grant_to": "Terminal, iTerm, Antigravity, or the app that launched scripts/relaunch_dev.sh",
                "installed_app_grant_to": "Sankalp.app when running from the installed app bundle",
                "accessibility_url": ACCESSIBILITY_URL,
                "screen_recording_url": SCREEN_RECORDING_URL,
            },
        }

    def list_apps(self) -> dict[str, Any]:
        if not self._is_macos():
            return {"apps": [], "error": "Computer Use is macOS-only in this build."}
        script = 'tell application "System Events" to get name of application processes whose background only is false'
        result = self._osascript(script)
        if result["returncode"] != 0:
            return {
                "apps": [],
                "error": result["stderr"] or result["stdout"] or "Could not list apps.",
                "hint": "Grant Accessibility permission to Sankalp or the launching terminal.",
            }
        apps = [item.strip() for item in result["stdout"].replace("\n", ",").split(",") if item.strip()]
        return {"apps": sorted(dict.fromkeys(apps)), "count": len(set(apps))}

    def open_app(self, app: str) -> dict[str, Any]:
        app = app.strip()
        if not app:
            return {"ok": False, "error": "app is required"}
        if not self._is_macos():
            return {"ok": False, "error": "Computer Use is macOS-only in this build."}
        result = subprocess.run(["open", "-a", app], text=True, capture_output=True, timeout=20)
        return {
            "ok": result.returncode == 0,
            "app": app,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    def open_permissions(self, target: str = "accessibility") -> dict[str, Any]:
        if not self._is_macos():
            return {"ok": False, "error": "Computer Use permissions are macOS-only."}
        target = target.strip().lower().replace("-", "_").replace(" ", "_")
        url = SCREEN_RECORDING_URL if target in {"screen", "screen_recording", "screenshot"} else ACCESSIBILITY_URL
        subprocess.Popen(["open", url])
        return {"ok": True, "target": target, "url": url}

    def inspect_app(self, app: str, max_depth: int = 3, max_children: int = 45) -> dict[str, Any]:
        app = app.strip()
        if not app:
            return {"app": app, "tree": "", "error": "app is required"}
        if not self._is_macos():
            return {"app": app, "tree": "", "error": "Computer Use is macOS-only in this build."}
        max_depth = max(0, min(int(max_depth or 3), 5))
        max_children = max(1, min(int(max_children or 45), 120))
        script = self._inspect_script(app, max_depth, max_children)
        result = self._osascript(script, timeout=30)
        if result["returncode"] != 0:
            return {
                "app": app,
                "tree": "",
                "error": result["stderr"] or result["stdout"] or "Could not inspect app.",
                "hint": "Grant Accessibility permission to Sankalp or the launching terminal.",
            }
        return {"app": app, "tree": result["stdout"].strip(), "format": "path role name value"}

    def screenshot(self) -> dict[str, Any]:
        if not self._is_macos():
            return {"ok": False, "error": "Computer Use screenshots are macOS-only in this build."}
        if not shutil.which("screencapture"):
            return {"ok": False, "error": "screencapture is not available."}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"screenshot-{int(time.time() * 1000)}.png"
        result = subprocess.run(["screencapture", "-x", str(path)], text=True, capture_output=True, timeout=20)
        if result.returncode != 0:
            return {
                "ok": False,
                "error": result.stderr.strip() or result.stdout.strip() or "Screenshot failed.",
                "hint": "Grant Screen Recording permission to Sankalp or the launching terminal.",
            }
        return {"ok": True, "path": str(path), "bytes": path.stat().st_size if path.exists() else 0}

    def click(self, app: str = "", element_path: str = "", x: int | None = None, y: int | None = None) -> dict[str, Any]:
        if x is not None and y is not None:
            output = self._native_click(int(x), int(y), app=app)
            if output.get("ok"):
                return {"action": "click", **output}
            script = f'tell application "System Events" to click at {{{int(x)}, {int(y)}}}'
            result = self._osascript(script)
            fallback = self._action_output("click", result, {"x": int(x), "y": int(y), "native": output})
            return fallback
        path = self._parse_element_path(element_path)
        if not path:
            return {"ok": False, "error": "element_path must be a dot-separated path like 1.2.3 or x/y coordinates are required"}
        script = self._element_script(app, path, 'try\n  perform action "AXPress" of currentElement\non error\n  click currentElement\nend try')
        result = self._osascript(script)
        return self._action_output("click", result, {"app": app, "element_path": element_path})

    def set_value(self, app: str, element_path: str, value: str) -> dict[str, Any]:
        path = self._parse_element_path(element_path)
        if not path:
            return {"ok": False, "error": "element_path must be a dot-separated path like 1.2.3"}
        script = self._element_script(app, path, f"set value of currentElement to {self._as_string(value)}")
        result = self._osascript(script)
        return self._action_output("set_value", result, {"app": app, "element_path": element_path})

    def type_text(self, app: str, element_path: str, text: str) -> dict[str, Any]:
        path = self._parse_element_path(element_path)
        if path:
            script = self._element_script(
                app,
                path,
                f"click currentElement\ndelay 0.1\nkeystroke {self._as_string(text)}",
            )
        else:
            script_lines = ['tell application "System Events"']
            if app.strip():
                script_lines.append(f"  tell process {self._as_string(app)} to set frontmost to true")
                script_lines.append("  delay 0.1")
            script_lines.append(f"  keystroke {self._as_string(text)}")
            script_lines.append("end tell")
            script = "\n".join(script_lines)
        result = self._osascript(script)
        return self._action_output("type_text", result, {"app": app, "element_path": element_path, "chars": len(text)})

    def press_key(self, app: str, key: str) -> dict[str, Any]:
        app = app.strip()
        key = key.strip()
        if not key:
            return {"ok": False, "error": "key is required"}
        script_lines = ['tell application "System Events"']
        if app:
            script_lines.append(f"  tell process {self._as_string(app)} to set frontmost to true")
            script_lines.append("  delay 0.1")
        key_script = self._key_script(key)
        if not key_script:
            return {"ok": False, "error": f"Unsupported key: {key}"}
        script_lines.append(f"  {key_script}")
        script_lines.append("end tell")
        result = self._osascript("\n".join(script_lines))
        return self._action_output("press_key", result, {"app": app, "key": key})

    def scroll(self, app: str, direction: str = "down", pages: int = 1) -> dict[str, Any]:
        direction = direction.strip().lower()
        key = {
            "down": "PageDown",
            "up": "PageUp",
            "left": "Left",
            "right": "Right",
        }.get(direction)
        if not key:
            return {"ok": False, "error": "direction must be one of down, up, left, right"}
        pages = max(1, min(int(pages or 1), 10))
        outputs = [self.press_key(app, key) for _ in range(pages)]
        ok = all(item.get("ok") for item in outputs)
        return {"ok": ok, "app": app, "direction": direction, "pages": pages, "steps": outputs}

    def wait(self, seconds: float = 1.0) -> dict[str, Any]:
        seconds = max(0.1, min(float(seconds or 1.0), 10.0))
        time.sleep(seconds)
        return {"ok": True, "seconds": seconds}

    def _is_macos(self) -> bool:
        return platform.system() == "Darwin"

    def _osascript(self, script: str, timeout: int = 15) -> dict[str, Any]:
        try:
            proc = subprocess.run(["osascript", "-e", script], text=True, capture_output=True, timeout=timeout)
            return {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}
        except Exception as exc:
            return {"returncode": 1, "stdout": "", "stderr": str(exc)}

    def _action_output(self, action: str, result: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": result["returncode"] == 0,
            "action": action,
            **extra,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        }

    def _native_click(self, x: int, y: int, app: str = "") -> dict[str, Any]:
        helper = self._click_helper()
        if not helper:
            return {"ok": False, "x": x, "y": y, "error": "native click helper is not available"}
        if app.strip():
            self._osascript(
                f'tell application "System Events" to tell process {self._as_string(app)} to set frontmost to true',
                timeout=5,
            )
            time.sleep(0.1)
        result = subprocess.run([str(helper), str(x), str(y)], text=True, capture_output=True, timeout=10)
        output: dict[str, Any] = {
            "ok": result.returncode == 0,
            "x": x,
            "y": y,
            "backend": "coregraphics-helper",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
        if result.stdout.strip():
            output.update(self._parse_helper_output(result.stdout.strip()))
        return output

    def _click_helper(self) -> Path | None:
        if not self._is_macos():
            return None
        helper = TOOLS_DIR / "sankalp-click"
        if helper.exists():
            return helper
        clang = shutil.which("clang")
        if not clang:
            return None
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        source = TOOLS_DIR / "sankalp-click.c"
        source.write_text(_CLICK_HELPER_SOURCE, encoding="utf-8")
        result = subprocess.run(
            [clang, str(source), "-O2", "-framework", "ApplicationServices", "-o", str(helper)],
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return helper if helper.exists() else None

    def _parse_helper_output(self, value: str) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for item in value.split():
            if "=" not in item:
                continue
            key, raw = item.split("=", 1)
            try:
                output[key] = float(raw) if "." in raw else int(raw)
            except ValueError:
                output[key] = raw
        return output

    def _inspect_script(self, app: str, max_depth: int, max_children: int) -> str:
        return f"""
using terms from application "System Events"
on cleanText(valueText)
  try
    set textValue to valueText as text
    set textValue to my replaceText(linefeed, " ", textValue)
    set textValue to my replaceText(return, " ", textValue)
    if (length of textValue) > 140 then set textValue to text 1 thru 140 of textValue
    return textValue
  on error
    return ""
  end try
end cleanText

on replaceText(findText, replacementText, sourceText)
  set AppleScript's text item delimiters to findText
  set textItems to text items of sourceText
  set AppleScript's text item delimiters to replacementText
  set joinedText to textItems as text
  set AppleScript's text item delimiters to ""
  return joinedText
end replaceText

on describeElement(currentElement, depth, elementPath, maxDepth, maxChildren)
  set elementRole to ""
  set elementName to ""
  set elementDescription to ""
  set elementValue to ""
  try
    set elementRole to role of currentElement as text
  end try
  try
    set elementName to my cleanText(name of currentElement)
  end try
  try
    set elementDescription to my cleanText(description of currentElement)
  end try
  try
    set elementValue to my cleanText(value of currentElement)
  end try
  set lineText to elementPath & " " & elementRole
  if elementName is not "" then
    set lineText to lineText & " name=" & (quoted form of elementName)
  end if
  if elementDescription is not "" then
    set lineText to lineText & " description=" & (quoted form of elementDescription)
  end if
  if elementValue is not "" then
    set lineText to lineText & " value=" & (quoted form of elementValue)
  end if
  set outputText to lineText & linefeed
  if depth >= maxDepth then
    return outputText
  end if
  try
    set childItems to UI elements of currentElement
    set childCount to count of childItems
    if childCount > maxChildren then
      set childCount to maxChildren
    end if
    repeat with childIndex from 1 to childCount
      set childPath to elementPath & "." & childIndex
      set outputText to outputText & my describeElement(item childIndex of childItems, depth + 1, childPath, maxDepth, maxChildren)
    end repeat
  end try
  return outputText
end describeElement

tell application "System Events"
  if not (exists process {self._as_string(app)}) then error "App process not found: {app}"
  tell process {self._as_string(app)}
    set frontmost to true
    delay 0.2
    if not (exists window 1) then
      return "App={app}" & linefeed & "No windows are available."
    end if
    set windowTitle to ""
    try
      set windowTitle to name of window 1 as text
    end try
    set outputText to "App={app}" & linefeed & "Window=" & (quoted form of windowTitle) & linefeed
    set outputText to outputText & my describeElement(window 1, 0, "1", {max_depth}, {max_children})
    return outputText
  end tell
end tell
end using terms from
"""

    def _element_script(self, app: str, path: list[int], action_body: str) -> str:
        if not app.strip():
            return 'error "app is required"'
        path_list = "{" + ", ".join(str(item) for item in path) + "}"
        return f"""
tell application "System Events"
  if not (exists process {self._as_string(app)}) then error "App process not found: {app}"
  tell process {self._as_string(app)}
    set frontmost to true
    delay 0.1
    set pathItems to {path_list}
    set currentElement to window (item 1 of pathItems)
    if (count of pathItems) > 1 then
      repeat with itemIndex from 2 to count of pathItems
        set currentElement to UI element (item itemIndex of pathItems) of currentElement
      end repeat
    end if
    {action_body}
  end tell
end tell
"""

    def _parse_element_path(self, element_path: str) -> list[int]:
        value = str(element_path or "").strip()
        if not re.fullmatch(r"\d+(?:\.\d+)*", value):
            return []
        return [int(part) for part in value.split(".")]

    def _key_script(self, key: str) -> str:
        normalized = key.strip().replace("+", "-").replace("_", "-").lower()
        parts = [part for part in normalized.split("-") if part]
        modifiers = [part for part in parts[:-1] if part in {"cmd", "command", "ctrl", "control", "alt", "option", "shift"}]
        base = parts[-1] if parts else normalized
        if modifiers and len(base) == 1:
            modifier_names = {
                "cmd": "command down",
                "command": "command down",
                "ctrl": "control down",
                "control": "control down",
                "alt": "option down",
                "option": "option down",
                "shift": "shift down",
            }
            using = "{" + ", ".join(modifier_names[item] for item in modifiers) + "}"
            return f"keystroke {self._as_string(base)} using {using}"
        key_codes = {
            "return": 36,
            "enter": 36,
            "tab": 48,
            "space": 49,
            "escape": 53,
            "esc": 53,
            "delete": 51,
            "backspace": 51,
            "left": 123,
            "right": 124,
            "down": 125,
            "up": 126,
            "pagedown": 121,
            "page-down": 121,
            "pageup": 116,
            "page-up": 116,
        }
        if normalized in key_codes:
            return f"key code {key_codes[normalized]}"
        if len(key) == 1:
            return f"keystroke {self._as_string(key)}"
        return ""

    def _as_string(self, value: str) -> str:
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
