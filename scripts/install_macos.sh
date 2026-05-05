#!/bin/sh
set -eu

DEFAULT_REPO_URL="https://github.com/RSWAIN1486/sankalp.git"
REPO_URL="${SANKALP_REPO_URL:-$DEFAULT_REPO_URL}"
BRANCH="${SANKALP_BRANCH:-main}"
INSTALL_DIR="${SANKALP_INSTALL_DIR:-$HOME/.sankalp/app}"
APP_PATH="${SANKALP_APP_PATH:-$HOME/Applications/Sankalp.app}"
SANKALP_HOST="${SANKALP_HOST:-127.0.0.1}"
SANKALP_PORT="${SANKALP_PORT:-8765}"
NODE_VERSION="${SANKALP_NODE_VERSION:-24}"
NVM_INSTALL_URL="${SANKALP_NVM_INSTALL_URL:-https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh}"
SOURCE_DIR="${SANKALP_SOURCE_DIR:-}"
USE_LOCAL_SOURCE=0
DEFAULT_INSTALL_DIR="$HOME/.sankalp/app"
PRESERVE_LOCAL_CHANGES="${SANKALP_PRESERVE_LOCAL_CHANGES:-0}"

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
  install_or_update_repo
  ensure_node
  build_webui
  free_port
  install_app_bundle
  open_app

  say "Sankalp is installed at $APP_PATH"
  say "WebUI: http://$SANKALP_HOST:$SANKALP_PORT"
  say "Logs: $HOME/.sankalp/Sankalp.app.log"
}

main "$@"
