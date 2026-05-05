from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

from sankalp.config import HOST, PORT, ROOT


FULL_DISK_ACCESS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
APP_PATH = Path("~/Applications/Sankalp.app").expanduser()
BUNDLE_ID = "ai.yantrai.sankalp"


def is_macos() -> bool:
    return platform.system() == "Darwin"


def macos_status() -> dict[str, Any]:
    return {
        "is_macos": is_macos(),
        "app_path": str(APP_PATH),
        "installed": APP_PATH.exists(),
        "full_disk_access_url": FULL_DISK_ACCESS_URL,
    }


def open_full_disk_access() -> dict[str, Any]:
    if not is_macos():
        return {"ok": False, "error": "Full Disk Access is macOS-specific."}
    subprocess.Popen(["open", FULL_DISK_ACCESS_URL])
    return {"ok": True, "url": FULL_DISK_ACCESS_URL}


def install_macos_app(app_path: Path = APP_PATH, repo_root: Path = ROOT) -> dict[str, Any]:
    if not is_macos():
        return {"ok": False, "error": "Sankalp.app can only be installed on macOS."}
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    (contents / "Info.plist").write_text(_plist(), encoding="utf-8")
    executable = macos_dir / "Sankalp"
    launcher_type = _write_native_launcher(executable, resources, repo_root.resolve())
    if launcher_type == "shell":
        executable.write_text(_launcher(repo_root.resolve()), encoding="utf-8")
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _codesign(app_path)
    return {
        "ok": True,
        "app_path": str(app_path),
        "bundle_id": BUNDLE_ID,
        "repo_root": str(repo_root.resolve()),
        "launcher_type": launcher_type,
    }


def _plist() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>Sankalp</string>
  <key>CFBundleIdentifier</key>
  <string>{BUNDLE_ID}</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>Sankalp</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>NSDocumentsFolderUsageDescription</key>
  <string>Sankalp reads your Obsidian vault when you configure memory sync.</string>
  <key>NSDesktopFolderUsageDescription</key>
  <string>Sankalp may read local workspace files you explicitly configure.</string>
  <key>NSDownloadsFolderUsageDescription</key>
  <string>Sankalp may read local workspace files you explicitly configure.</string>
</dict>
</plist>
"""


def _write_native_launcher(executable: Path, resources: Path, repo_root: Path) -> str:
    clang = shutil.which("clang")
    if not clang:
        return "shell"
    source = resources / "launcher.c"
    source.write_text(_native_launcher_source(repo_root), encoding="utf-8")
    result = subprocess.run(
        [clang, str(source), "-O2", "-o", str(executable)],
        text=True,
        capture_output=True,
        timeout=60,
    )
    if result.returncode != 0:
        return "shell"
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return "native"


def _codesign(app_path: Path) -> None:
    codesign = shutil.which("codesign")
    if not codesign:
        return
    subprocess.run(
        [codesign, "--force", "--deep", "--sign", "-", str(app_path)],
        text=True,
        capture_output=True,
        timeout=60,
    )


def _native_launcher_source(repo_root: Path) -> str:
    return f'''#include <crt_externs.h>
#include <errno.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static int run_quiet(const char *cmd) {{
  int rc = system(cmd);
  if (rc == -1) return 1;
  if (WIFEXITED(rc)) return WEXITSTATUS(rc);
  return 1;
}}

static void open_url(void) {{
  pid_t pid;
  char *argv[] = {{"/usr/bin/open", "http://{HOST}:{PORT}", NULL}};
  posix_spawn(&pid, "/usr/bin/open", NULL, NULL, argv, environ);
}}

static void free_port(void) {{
  run_quiet("/bin/sh -c 'pids=$(/usr/sbin/lsof -tiTCP:{PORT} -sTCP:LISTEN 2>/dev/null); [ -z \"$pids\" ] || /bin/kill -TERM $pids >/dev/null 2>&1'");
  usleep(500000);
  run_quiet("/bin/sh -c 'pids=$(/usr/sbin/lsof -tiTCP:{PORT} -sTCP:LISTEN 2>/dev/null); [ -z \"$pids\" ] || /bin/kill -KILL $pids >/dev/null 2>&1'");
}}

int main(void) {{
  const char *repo = "{repo_root}";
  const char *home = getenv("HOME");
  char log_dir[4096];
  char log_file[4096];
  char health_cmd[512];

  snprintf(health_cmd, sizeof(health_cmd), "/usr/bin/curl -fsS http://{HOST}:{PORT}/api/health >/dev/null 2>&1");
  if (run_quiet(health_cmd) == 0) {{
    open_url();
    return 0;
  }}
  free_port();

  if (!home) home = "/tmp";
  snprintf(log_dir, sizeof(log_dir), "%s/.sankalp", home);
  mkdir(log_dir, 0700);
  snprintf(log_file, sizeof(log_file), "%s/Sankalp.app.log", log_dir);

  int fd = open(log_file, O_CREAT | O_WRONLY | O_APPEND, 0600);
  if (fd < 0) fd = open("/dev/null", O_WRONLY);

  posix_spawn_file_actions_t actions;
  posix_spawn_file_actions_init(&actions);
  posix_spawn_file_actions_adddup2(&actions, fd, STDOUT_FILENO);
  posix_spawn_file_actions_adddup2(&actions, fd, STDERR_FILENO);
  posix_spawn_file_actions_addclose(&actions, fd);

  posix_spawnattr_t attrs;
  posix_spawnattr_init(&attrs);
  posix_spawnattr_setflags(&attrs, POSIX_SPAWN_SETSID);

  chdir(repo);
  setenv("SANKALP_HOST", "{HOST}", 0);
  setenv("SANKALP_PORT", "{PORT}", 0);
  setenv("SANKALP_REPO_DIR", repo, 1);

  pid_t server_pid;
  char *argv[] = {{"/usr/bin/python3", "server.py", NULL}};
  int spawn_rc = posix_spawn(&server_pid, "/usr/bin/python3", &actions, &attrs, argv, environ);
  posix_spawn_file_actions_destroy(&actions);
  posix_spawnattr_destroy(&attrs);
  if (fd >= 0) close(fd);

  if (spawn_rc != 0) {{
    return spawn_rc;
  }}

  for (int i = 0; i < 80; i++) {{
    if (run_quiet(health_cmd) == 0) {{
      open_url();
      return 0;
    }}
    usleep(250000);
  }}
  return 0;
}}
'''


def _launcher(repo_root: Path) -> str:
    return f"""#!/bin/zsh
set -u

export SANKALP_HOST="${{SANKALP_HOST:-{HOST}}}"
export SANKALP_PORT="${{SANKALP_PORT:-{PORT}}}"
export SANKALP_REPO_DIR="{repo_root}"

LOG_DIR="$HOME/.sankalp"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/Sankalp.app.log"
URL="http://${{SANKALP_HOST}}:${{SANKALP_PORT}}"

if /usr/bin/curl -fsS "$URL/api/health" >/dev/null 2>&1; then
  /usr/bin/open "$URL"
  exit 0
fi

free_port() {{
  local pids
  pids="$(/usr/sbin/lsof -tiTCP:"$SANKALP_PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    /bin/kill -TERM $pids >/dev/null 2>&1 || true
    /bin/sleep 0.5
  fi
  pids="$(/usr/sbin/lsof -tiTCP:"$SANKALP_PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    /bin/kill -KILL $pids >/dev/null 2>&1 || true
  fi
}}

free_port

cd "$SANKALP_REPO_DIR" || exit 1
nohup /usr/bin/python3 server.py >>"$LOG_FILE" 2>&1 </dev/null &
SERVER_PID=$!

for _ in {{1..60}}; do
  if /usr/bin/curl -fsS "$URL/api/health" >/dev/null 2>&1; then
    /usr/bin/open "$URL"
    exit 0
  fi
  /bin/sleep 0.25
done

if /bin/kill -0 "$SERVER_PID" >/dev/null 2>&1; then
  /usr/bin/open "$URL"
  exit 0
fi

exit 1
"""
