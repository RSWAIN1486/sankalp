#!/bin/sh
set -eu

DEFAULT_REPO_URL="https://github.com/RSWAIN1486/sankalp.git"
REPO_URL="${SANKALP_REPO_URL:-$DEFAULT_REPO_URL}"
BRANCH="${SANKALP_BRANCH:-main}"
AGENT_HOME="${SANKALP_AGENT_HOME:-${SANKALP_STATE_DIR:-$HOME/.sankalp}}"
INSTALL_DIR="${SANKALP_INSTALL_DIR:-$AGENT_HOME/app}"
APP_PATH="${SANKALP_APP_PATH:-$HOME/Applications/Sankalp.app}"
SANKALP_HOST="${SANKALP_HOST:-127.0.0.1}"
SANKALP_PORT="${SANKALP_PORT:-8765}"
NODE_VERSION="${SANKALP_NODE_VERSION:-24}"
NVM_INSTALL_URL="${SANKALP_NVM_INSTALL_URL:-https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh}"
SOURCE_DIR="${SANKALP_SOURCE_DIR:-}"
USE_LOCAL_SOURCE=0
DEFAULT_INSTALL_DIR="$AGENT_HOME/app"
PRESERVE_LOCAL_CHANGES="${SANKALP_PRESERVE_LOCAL_CHANGES:-0}"
OBSIDIAN_ONBOARD="${SANKALP_OBSIDIAN_ONBOARD:-1}"
LAUNCH_AGENT_LABEL="${SANKALP_LAUNCH_AGENT_LABEL:-ai.yantrai.sankalp.daemon}"

say() {
  printf '%s\n' "$1"
}

need_macos() {
  if [ "$(uname -s)" != "Darwin" ]; then
    say "Sankalp.app installation is currently macOS-only."
    exit 1
  fi
}

need_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    say "Missing required tool: $1"
    exit 1
  fi
}

detect_local_source() {
  if [ -n "$SOURCE_DIR" ]; then
    SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"
    USE_LOCAL_SOURCE=1
    return
  fi

  case "$0" in
    */install_macos.sh|install_macos.sh)
      script_dir="$(cd "$(dirname "$0")" && pwd)"
      candidate="$(cd "$script_dir/.." && pwd)"
      if [ -d "$candidate/sankalp" ] && [ -d "$candidate/web" ] && [ -z "${SANKALP_REPO_URL+x}" ]; then
        SOURCE_DIR="$candidate"
        USE_LOCAL_SOURCE=1
      fi
      ;;
  esac
}

is_repo_checkout() {
  [ -d "$1/.git" ] && [ -d "$1/sankalp" ] && [ -d "$1/web" ]
}

migrate_legacy_home() {
  legacy_home="$HOME/sankalp"
  if [ ! -e "$legacy_home" ]; then
    return
  fi
  if [ "$USE_LOCAL_SOURCE" = "1" ] && [ "$(cd "$legacy_home" 2>/dev/null && pwd || true)" = "$SOURCE_DIR" ]; then
    say "Keeping local source checkout at $legacy_home"
    return
  fi

  mkdir -p "$AGENT_HOME"
  if is_repo_checkout "$legacy_home" && [ ! -e "$INSTALL_DIR" ]; then
    say "Migrating legacy Sankalp checkout from $legacy_home to $INSTALL_DIR"
    mv "$legacy_home" "$INSTALL_DIR"
    return
  fi

  if [ ! -e "$AGENT_HOME" ] || [ -z "$(find "$AGENT_HOME" -mindepth 1 -maxdepth 1 2>/dev/null | head -n 1)" ]; then
    say "Migrating legacy Sankalp home from $legacy_home to $AGENT_HOME"
    rmdir "$AGENT_HOME" 2>/dev/null || true
    mv "$legacy_home" "$AGENT_HOME"
    return
  fi

  backup="$AGENT_HOME/legacy-sankalp-$(date +%Y%m%d%H%M%S)"
  say "Moving legacy Sankalp folder to $backup"
  mv "$legacy_home" "$backup"
}

install_or_update_repo() {
  mkdir -p "$(dirname "$INSTALL_DIR")"

  if [ "$USE_LOCAL_SOURCE" = "1" ]; then
    need_tool rsync
    say "Installing Sankalp from local checkout $SOURCE_DIR"
    mkdir -p "$INSTALL_DIR"
    rsync -a --delete \
      --exclude ".git/" \
      --exclude "web/node_modules/" \
      --exclude "web/.svelte-kit/" \
      --exclude "web/build/" \
      "$SOURCE_DIR/" "$INSTALL_DIR/"
    return
  fi

  if [ -d "$INSTALL_DIR/.git" ]; then
    say "Updating Sankalp in $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch --prune origin
    if [ "$INSTALL_DIR" = "$DEFAULT_INSTALL_DIR" ] || [ "${SANKALP_FORCE_UPDATE:-0}" = "1" ]; then
      if [ "$PRESERVE_LOCAL_CHANGES" != "1" ]; then
        # Managed installs should always recover from dirty local edits.
        git -C "$INSTALL_DIR" reset --hard HEAD
        git -C "$INSTALL_DIR" clean -fd
      else
        say "Preserving local changes in managed checkout because SANKALP_PRESERVE_LOCAL_CHANGES=1"
      fi
      git -C "$INSTALL_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
      if [ "$PRESERVE_LOCAL_CHANGES" != "1" ]; then
        git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
        git -C "$INSTALL_DIR" clean -fd
      fi
    else
      git -C "$INSTALL_DIR" checkout "$BRANCH"
      git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
    fi
  else
    if [ -e "$INSTALL_DIR" ]; then
      say "$INSTALL_DIR exists but is not a git checkout."
      say "Move it aside or set SANKALP_INSTALL_DIR to another location."
      exit 1
    fi
    say "Installing Sankalp into $INSTALL_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  fi
}

load_nvm() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [ -s "$NVM_DIR/nvm.sh" ]; then
    # shellcheck disable=SC1091
    . "$NVM_DIR/nvm.sh"
  fi
}

ensure_node() {
  load_nvm
  if command -v nvm >/dev/null 2>&1; then
    nvm install "$NODE_VERSION"
    nvm use "$NODE_VERSION"
    return
  fi

  if command -v node >/dev/null 2>&1; then
    node_major="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || printf '0')"
    if [ "$node_major" -ge 20 ]; then
      return
    fi
  fi

  say "Installing nvm so Sankalp can build the WebUI with Node $NODE_VERSION"
  mkdir -p "$NVM_DIR"
  curl -fsSL "$NVM_INSTALL_URL" | bash
  load_nvm
  if ! command -v nvm >/dev/null 2>&1; then
    say "nvm installation did not become available in this shell."
    exit 1
  fi
  nvm install "$NODE_VERSION"
  nvm use "$NODE_VERSION"
}

build_webui() {
  say "Installing WebUI dependencies"
  (
    cd "$INSTALL_DIR/web"
    npm ci
    npm exec svelte-kit sync
    npm run build
  )
}

free_port() {
  if [ "${SANKALP_SKIP_PORT_KILL:-0}" = "1" ]; then
    return
  fi
  if ! command -v lsof >/dev/null 2>&1; then
    return
  fi

  pids="$(lsof -tiTCP:"$SANKALP_PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    return
  fi

  say "Freeing local port $SANKALP_PORT"
  kill -TERM $pids >/dev/null 2>&1 || true
  sleep 1
  pids="$(lsof -tiTCP:"$SANKALP_PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    kill -KILL $pids >/dev/null 2>&1 || true
  fi
}

install_app_bundle() {
  say "Installing Sankalp.app"
  (
    cd "$INSTALL_DIR"
    SANKALP_HOST="$SANKALP_HOST" SANKALP_PORT="$SANKALP_PORT" SANKALP_APP_PATH="$APP_PATH" SANKALP_INSTALL_DIR="$INSTALL_DIR" python3 -c 'import os; from pathlib import Path; from sankalp.macos import install_macos_app; result = install_macos_app(app_path=Path(os.environ["SANKALP_APP_PATH"]), repo_root=Path(os.environ["SANKALP_INSTALL_DIR"])); print(result)'
  )
}

install_launch_agent() {
  if [ "${SANKALP_INSTALL_LAUNCH_AGENT:-1}" != "1" ]; then
    return
  fi

  launch_agents_dir="$HOME/Library/LaunchAgents"
  plist_path="$launch_agents_dir/$LAUNCH_AGENT_LABEL.plist"
  mkdir -p "$launch_agents_dir" "$AGENT_HOME/logs"

  say "Installing Sankalp login daemon"
  LAUNCH_AGENT_PLIST="$plist_path" \
  LAUNCH_AGENT_LABEL="$LAUNCH_AGENT_LABEL" \
  SANKALP_INSTALL_DIR="$INSTALL_DIR" \
  SANKALP_AGENT_HOME="$AGENT_HOME" \
  SANKALP_HOST="$SANKALP_HOST" \
  SANKALP_PORT="$SANKALP_PORT" \
  SANKALP_APP_PATH="$APP_PATH" \
  python3 - <<'PY'
import os
import plistlib
from pathlib import Path

plist_path = Path(os.environ["LAUNCH_AGENT_PLIST"])
install_dir = os.environ["SANKALP_INSTALL_DIR"]
agent_home = os.environ["SANKALP_AGENT_HOME"]
host = os.environ["SANKALP_HOST"]
port = os.environ["SANKALP_PORT"]
app_path = os.environ["SANKALP_APP_PATH"]
app_executable = str(Path(app_path) / "Contents" / "MacOS" / "Sankalp")
payload = {
    "Label": os.environ["LAUNCH_AGENT_LABEL"],
    "ProgramArguments": [app_executable],
    "RunAtLoad": True,
    "KeepAlive": True,
    "WorkingDirectory": install_dir,
    "StandardOutPath": str(Path(agent_home) / "logs" / "Sankalp.daemon.log"),
    "StandardErrorPath": str(Path(agent_home) / "logs" / "Sankalp.daemon.err.log"),
    "EnvironmentVariables": {
        "SANKALP_HOST": host,
        "SANKALP_PORT": port,
        "SANKALP_STATE_DIR": agent_home,
        "SANKALP_APP_PATH": app_path,
        "SANKALP_MENU_BAR_LOGIN": "1",
    },
}
with plist_path.open("wb") as handle:
    plistlib.dump(payload, handle)
PY

  uid="$(id -u)"
  launchctl bootout "gui/$uid" "$plist_path" >/dev/null 2>&1 || launchctl unload "$plist_path" >/dev/null 2>&1 || true
  if ! launchctl bootstrap "gui/$uid" "$plist_path" >/dev/null 2>&1; then
    launchctl load "$plist_path" >/dev/null 2>&1 || true
  fi
  launchctl kickstart -k "gui/$uid/$LAUNCH_AGENT_LABEL" >/dev/null 2>&1 || true
}

obsidian_onboarding() {
  if [ "$OBSIDIAN_ONBOARD" = "0" ]; then
    return
  fi
  say "Checking Obsidian setup"
  (
    cd "$INSTALL_DIR"
    SANKALP_OBSIDIAN_ONBOARD="$OBSIDIAN_ONBOARD" python3 - <<'PY'
import os
from sankalp.macos import obsidian_status, open_obsidian_download, request_vault_access
from sankalp.settings import auto_detect_obsidian_vault, load_settings, save_settings

status = obsidian_status()
if not status.get("installed"):
    print("Obsidian is not installed. Opening download page.")
    open_obsidian_download()
    raise SystemExit(0)

current_path = str(load_settings().get("obsidian_vault_path") or "").strip()
detected_path = auto_detect_obsidian_vault(accessible_only=True)
if detected_path and detected_path != current_path:
    save_settings({"obsidian_vault_path": detected_path})
    print(f"Auto-detected Obsidian vault: {detected_path}")

if os.environ.get("SANKALP_OBSIDIAN_ONBOARD", "1") == "prompt":
    default_path = str(load_settings().get("obsidian_vault_path") or "")
    result = request_vault_access(default_path)
    if result.get("ok") and result.get("path"):
        save_settings({"obsidian_vault_path": str(result["path"])})
        print(f"Configured Obsidian vault: {result['path']}")
    elif result.get("cancelled"):
        print("Obsidian vault selection cancelled.")
    else:
        print(f"Could not configure Obsidian vault: {result.get('error')}")
PY
  )
}

open_app() {
  if [ "${SANKALP_OPEN_AFTER_INSTALL:-1}" = "1" ]; then
    say "Opening Sankalp.app"
    open "$APP_PATH"
  fi
}

main() {
  need_macos
  need_tool git
  need_tool curl
  need_tool python3
  need_tool bash

  detect_local_source
  migrate_legacy_home
  install_or_update_repo
  ensure_node
  build_webui
  free_port
  install_app_bundle
  install_launch_agent
  obsidian_onboarding
  open_app

  say "Sankalp is installed at $APP_PATH"
  say "WebUI: http://$SANKALP_HOST:$SANKALP_PORT"
  say "Logs: $AGENT_HOME/logs/Sankalp.app.log"
  say "Daemon logs: $AGENT_HOME/logs/Sankalp.daemon.log"
}

main "$@"
