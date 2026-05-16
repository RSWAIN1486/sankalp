from __future__ import annotations

import os
import platform
import shlex
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

from sankalp.config import HOST, PORT, ROOT


FULL_DISK_ACCESS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
OBSIDIAN_DOWNLOAD_URL = "https://obsidian.md/download"
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


def obsidian_status() -> dict[str, Any]:
    app_paths = [
        Path("/Applications/Obsidian.app"),
        Path("~/Applications/Obsidian.app").expanduser(),
    ]
    installed_path = next((path for path in app_paths if path.exists()), None)
    return {
        "installed": installed_path is not None,
        "app_path": str(installed_path) if installed_path else "",
        "download_url": OBSIDIAN_DOWNLOAD_URL,
    }


def open_obsidian_download() -> dict[str, Any]:
    if not is_macos():
        return {"ok": False, "error": "Obsidian install helper is macOS-specific."}
    subprocess.Popen(["open", OBSIDIAN_DOWNLOAD_URL])
    return {"ok": True, "url": OBSIDIAN_DOWNLOAD_URL}


def request_vault_access(default_path: str = "") -> dict[str, Any]:
    if not is_macos():
        return {"ok": False, "error": "Vault access prompt is macOS-specific."}
    if not shutil.which("osascript"):
        return {"ok": False, "error": "osascript is required on macOS."}

    default_folder = Path(default_path).expanduser() if default_path else Path.home() / "Documents"
    if not default_folder.exists():
        default_folder = Path.home()
    if default_folder.is_file():
        default_folder = default_folder.parent
    default_folder = default_folder.resolve()

    script = (
        'set selectedFolder to choose folder with prompt '
        '"Select your Obsidian vault folder to grant Sankalp access." '
        f'default location POSIX file "{str(default_folder).replace(chr(34), chr(92) + chr(34))}"\n'
        "return POSIX path of selectedFolder\n"
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Vault selection was cancelled.").strip()
        if "User canceled" in message:
            return {"ok": False, "cancelled": True, "error": "Vault selection cancelled."}
        return {"ok": False, "error": message}
    selected = (result.stdout or "").strip()
    if not selected:
        return {"ok": False, "error": "No folder selected."}
    return {"ok": True, "path": selected.rstrip("/")}


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
  <key>LSUIElement</key>
  <true/>
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
    source = resources / "launcher.m"
    source.write_text(_native_launcher_source(repo_root), encoding="utf-8")
    result = subprocess.run(
        [clang, str(source), "-fobjc-arc", "-framework", "Cocoa", "-O2", "-o", str(executable)],
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
    repo = str(repo_root)
    repo_shell = shlex.quote(repo)
    repo_objc = _objc_string(repo)
    repo_shell_objc = _objc_string(repo_shell)
    app_path_objc = _objc_string(str(APP_PATH))
    app_path_shell_objc = _objc_string(shlex.quote(str(APP_PATH)))
    return f'''#import <Cocoa/Cocoa.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static NSString * const SankalpURL = @"http://{HOST}:{PORT}";
static NSString * const SankalpRepo = @"{repo_objc}";
static NSString * const SankalpBaseURL = @"localhost:{PORT}";
static int SankalpLockFD = -1;

static int run_quiet(NSString *cmd) {{
  int rc = system([cmd UTF8String]);
  if (rc == -1) return 1;
  if (WIFEXITED(rc)) return WEXITSTATUS(rc);
  return 1;
}}

static BOOL sankalp_live(void) {{
  return run_quiet(@"/usr/bin/curl -fsS http://{HOST}:{PORT}/api/health >/dev/null 2>&1") == 0;
}}

static NSDictionary *sankalp_update_status(void) {{
  NSURL *url = [NSURL URLWithString:[SankalpURL stringByAppendingString:@"/api/app/update"]];
  NSData *data = [NSData dataWithContentsOfURL:url options:0 error:nil];
  if (!data) return nil;
  id parsed = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  if (![parsed isKindOfClass:[NSDictionary class]]) return nil;
  id update = [(NSDictionary *)parsed objectForKey:@"update"];
  if (![update isKindOfClass:[NSDictionary class]]) return nil;
  return (NSDictionary *)update;
}}

static void start_update(void) {{
  run_quiet(@"/usr/bin/curl -fsS -X POST -H 'Content-Type: application/json' -d '{{}}' http://{HOST}:{PORT}/api/app/update >/dev/null 2>&1 &");
}}

static void open_webui(void) {{
  [[NSWorkspace sharedWorkspace] openURL:[NSURL URLWithString:SankalpURL]];
}}

static NSImage *sankalp_icon(BOOL live) {{
  NSImage *image = [[NSImage alloc] initWithSize:NSMakeSize(18, 18)];
  [image lockFocus];
  NSBezierPath *background = [NSBezierPath bezierPathWithRoundedRect:NSMakeRect(1, 1, 16, 16) xRadius:4 yRadius:4];
  NSColor *fill = live
    ? [NSColor colorWithCalibratedRed:0.18 green:0.47 blue:0.86 alpha:1.0]
    : [NSColor colorWithCalibratedWhite:0.45 alpha:1.0];
  [fill setFill];
  [background fill];

  [[NSColor whiteColor] setStroke];
  NSBezierPath *mark = [NSBezierPath bezierPath];
  mark.lineWidth = 2.0;
  mark.lineCapStyle = NSLineCapStyleRound;
  mark.lineJoinStyle = NSLineJoinStyleRound;
  [mark moveToPoint:NSMakePoint(6, 12)];
  [mark lineToPoint:NSMakePoint(11, 9)];
  [mark lineToPoint:NSMakePoint(7, 5)];
  [mark stroke];

  [image unlockFocus];
  image.template = NO;
  return image;
}}

static BOOL login_launch(void) {{
  const char *value = getenv("SANKALP_MENU_BAR_LOGIN");
  return value && strcmp(value, "1") == 0;
}}

static BOOL acquire_single_instance_lock(void) {{
  const char *home = getenv("HOME");
  if (!home) home = "/tmp";
  char state_dir[4096];
  char lock_path[4096];
  snprintf(state_dir, sizeof(state_dir), "%s/.sankalp", home);
  mkdir(state_dir, 0700);
  snprintf(lock_path, sizeof(lock_path), "%s/Sankalp.menu.lock", state_dir);
  SankalpLockFD = open(lock_path, O_CREAT | O_RDWR, 0600);
  if (SankalpLockFD < 0) return YES;
  if (flock(SankalpLockFD, LOCK_EX | LOCK_NB) != 0) {{
    close(SankalpLockFD);
    SankalpLockFD = -1;
    return NO;
  }}
  return YES;
}}

static void free_port(void) {{
  run_quiet(@"/bin/sh -c 'pids=$(/usr/sbin/lsof -tiTCP:{PORT} -sTCP:LISTEN 2>/dev/null); [ -z \\"$pids\\" ] || /bin/kill -TERM $pids >/dev/null 2>&1'");
  [NSThread sleepForTimeInterval:0.5];
  run_quiet(@"/bin/sh -c 'pids=$(/usr/sbin/lsof -tiTCP:{PORT} -sTCP:LISTEN 2>/dev/null); [ -z \\"$pids\\" ] || /bin/kill -KILL $pids >/dev/null 2>&1'");
}}

static void start_daemon(void) {{
  if (sankalp_live()) return;
  run_quiet(@"mkdir -p \\"$HOME/.sankalp/logs\\"");
  NSString *cmd =
    @"cd {repo_shell_objc} && "
    @"SANKALP_HOST={HOST} SANKALP_PORT={PORT} "
    @"SANKALP_REPO_DIR={repo_shell_objc} "
    @"SANKALP_APP_PATH={app_path_shell_objc} "
    @"nohup /usr/bin/python3 -m sankalp.daemon >>\\"$HOME/.sankalp/logs/Sankalp.app.log\\" 2>&1 </dev/null &";
  run_quiet(cmd);
}}

@interface SankalpAppDelegate : NSObject <NSApplicationDelegate>
@property(nonatomic, strong) NSStatusItem *statusItem;
@property(nonatomic, strong) NSMenuItem *statusLine;
@property(nonatomic, strong) NSMenuItem *baseURLLine;
@property(nonatomic, strong) NSMenuItem *updateItem;
@property(nonatomic, strong) NSTimer *timer;
@property(nonatomic, strong) NSTimer *updateTimer;
@end

@implementation SankalpAppDelegate

- (void)applicationDidFinishLaunching:(NSNotification *)notification {{
  [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
  self.statusItem = [[NSStatusBar systemStatusBar] statusItemWithLength:NSVariableStatusItemLength];
  self.statusItem.button.title = @"";
  self.statusItem.button.image = sankalp_icon(YES);
  self.statusItem.button.imagePosition = NSImageOnly;
  self.statusItem.button.toolTip = @"Sankalp";

  NSMenu *menu = [[NSMenu alloc] initWithTitle:@"Sankalp"];
  NSMenuItem *titleLine = [[NSMenuItem alloc] initWithTitle:@"Sankalp" action:nil keyEquivalent:@""];
  titleLine.enabled = NO;
  [menu addItem:titleLine];
  self.statusLine = [[NSMenuItem alloc] initWithTitle:@"Status: Checking..." action:nil keyEquivalent:@""];
  self.statusLine.enabled = NO;
  [menu addItem:self.statusLine];
  [menu addItem:[self baseURLMenuItem]];
  [menu addItem:[NSMenuItem separatorItem]];
  self.updateItem = [[NSMenuItem alloc] initWithTitle:@"Update Sankalp" action:@selector(updateSankalp:) keyEquivalent:@"u"];
  self.updateItem.hidden = YES;
  [menu addItem:self.updateItem];
  [menu addItem:[[NSMenuItem alloc] initWithTitle:@"Open WebUI" action:@selector(openWebUI:) keyEquivalent:@"o"]];
  [menu addItem:[[NSMenuItem alloc] initWithTitle:@"Restart Daemon" action:@selector(restartDaemon:) keyEquivalent:@"r"]];
  self.statusItem.menu = menu;

  start_daemon();
  [self refreshStatus:nil];
  [self refreshUpdateStatus:nil];
  self.timer = [NSTimer scheduledTimerWithTimeInterval:5.0 target:self selector:@selector(refreshStatus:) userInfo:nil repeats:YES];
  self.updateTimer = [NSTimer scheduledTimerWithTimeInterval:1800.0 target:self selector:@selector(refreshUpdateStatus:) userInfo:nil repeats:YES];
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 3 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{{
    [self refreshUpdateStatus:nil];
  }});

  if (!login_launch()) {{
    open_webui();
  }}
}}

- (void)refreshStatus:(id)sender {{
  BOOL live = sankalp_live();
  self.statusItem.button.title = @"";
  self.statusItem.button.image = sankalp_icon(live);
  self.statusLine.title = live ? @"Status: Live" : @"Status: Offline";
}}

- (void)refreshUpdateStatus:(id)sender {{
  if (!sankalp_live()) {{
    self.updateItem.hidden = YES;
    return;
  }}

  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{{
    NSDictionary *update = sankalp_update_status();
    BOOL available = [[update objectForKey:@"update_available"] boolValue];
    id latestValue = [update objectForKey:@"latest_version"];
    NSString *latest = [latestValue isKindOfClass:[NSString class]] ? (NSString *)latestValue : @"";

    dispatch_async(dispatch_get_main_queue(), ^{{
      if (!available) {{
        self.updateItem.hidden = YES;
        return;
      }}
      self.updateItem.hidden = NO;
      self.updateItem.enabled = YES;
      self.updateItem.title = [latest length] > 0
        ? [NSString stringWithFormat:@"Update Sankalp (%@)", latest]
        : @"Update Sankalp";
    }});
  }});
}}

- (NSMenuItem *)baseURLMenuItem {{
  NSMenuItem *item = [[NSMenuItem alloc] initWithTitle:@"" action:nil keyEquivalent:@""];
  NSView *view = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 260, 28)];
  NSTextField *label = [[NSTextField alloc] initWithFrame:NSMakeRect(14, 4, 168, 20)];
  label.stringValue = [NSString stringWithFormat:@"Base URL: %@", SankalpBaseURL];
  label.editable = NO;
  label.bordered = NO;
  label.drawsBackground = NO;
  label.font = [NSFont systemFontOfSize:13];
  label.textColor = [NSColor labelColor];
  NSButton *copyButton = [NSButton buttonWithTitle:@"Copy" target:self action:@selector(copyBaseURL:)];
  copyButton.frame = NSMakeRect(192, 2, 58, 24);
  copyButton.bezelStyle = NSBezelStyleRounded;
  [view addSubview:label];
  [view addSubview:copyButton];
  item.view = view;
  return item;
}}

- (void)copyBaseURL:(id)sender {{
  NSPasteboard *pasteboard = [NSPasteboard generalPasteboard];
  [pasteboard clearContents];
  [pasteboard setString:SankalpURL forType:NSPasteboardTypeString];
}}

- (void)updateSankalp:(id)sender {{
  self.updateItem.hidden = NO;
  self.updateItem.enabled = NO;
  self.updateItem.title = @"Update started...";
  start_update();
}}

- (void)openWebUI:(id)sender {{
  start_daemon();
  open_webui();
  [self refreshStatus:nil];
  [self refreshUpdateStatus:nil];
}}

- (void)restartDaemon:(id)sender {{
  free_port();
  start_daemon();
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{{
    [self refreshStatus:nil];
    [self refreshUpdateStatus:nil];
  }});
}}

@end

int main(int argc, const char * argv[]) {{
  @autoreleasepool {{
    if (!acquire_single_instance_lock()) {{
      if (!login_launch()) open_webui();
      return 0;
    }}
    NSApplication *app = [NSApplication sharedApplication];
    SankalpAppDelegate *delegate = [[SankalpAppDelegate alloc] init];
    app.delegate = delegate;
    [app run];
  }}
  return 0;
}}
'''


def _objc_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _launcher(repo_root: Path) -> str:
    return f"""#!/bin/zsh
set -u

export SANKALP_HOST="${{SANKALP_HOST:-{HOST}}}"
export SANKALP_PORT="${{SANKALP_PORT:-{PORT}}}"
export SANKALP_REPO_DIR="{repo_root}"

LOG_DIR="$HOME/.sankalp/logs"
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
nohup /usr/bin/python3 -m sankalp.daemon >>"$LOG_FILE" 2>&1 </dev/null &
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
