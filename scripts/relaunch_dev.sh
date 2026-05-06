#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
BACKEND_HOST="${SANKALP_HOST:-127.0.0.1}"
BACKEND_PORT="${SANKALP_PORT:-8765}"
FRONTEND_HOST="${SANKALP_WEB_HOST:-127.0.0.1}"
FRONTEND_PORT="${SANKALP_WEB_PORT:-5173}"
LOG_DIR="${SANKALP_DEV_LOG_DIR:-$ROOT_DIR/.dev-logs}"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

say() {
  printf '%s\n' "$1"
}

kill_by_pid_file() {
  pid_file="$1"
  if [ ! -f "$pid_file" ]; then
    return
  fi
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -z "$pid" ]; then
    rm -f "$pid_file"
    return
  fi
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill -TERM "$pid" >/dev/null 2>&1 || true
    sleep 1
    kill -0 "$pid" >/dev/null 2>&1 && kill -KILL "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$pid_file"
}

kill_port() {
  port="$1"
  if ! command -v lsof >/dev/null 2>&1; then
    return
  fi
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    return
  fi
  say "Freeing port $port"
  kill -TERM $pids >/dev/null 2>&1 || true
  sleep 1
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  [ -n "$pids" ] && kill -KILL $pids >/dev/null 2>&1 || true
}

need_tool() {
  if ! command -v "$1" >/dev/null 2>&1; then
    say "Missing required tool: $1"
    exit 1
  fi
}

is_port_listening() {
  port="$1"
  if ! command -v lsof >/dev/null 2>&1; then
    return 1
  fi
  lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_port() {
  port="$1"
  timeout="${2:-20}"
  i=0
  while [ "$i" -lt "$timeout" ]; do
    if is_port_listening "$port"; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

open_frontend() {
  url="http://$FRONTEND_HOST:$FRONTEND_PORT"
  if command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || true
    return
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
    return
  fi
  say "Frontend URL: $url"
}

ensure_node() {
  nvm_dir="${NVM_DIR:-$HOME/.nvm}"
  node_version_file="$ROOT_DIR/web/.nvmrc"

  if [ -s "$nvm_dir/nvm.sh" ]; then
    # shellcheck disable=SC1090
    . "$nvm_dir/nvm.sh"
  fi

  if command -v nvm >/dev/null 2>&1; then
    # Prefer project-pinned Node version and refresh npm on that runtime.
    if [ -f "$node_version_file" ]; then
      node_version="$(tr -d '[:space:]' <"$node_version_file")"
      if [ -n "$node_version" ]; then
        nvm install "$node_version" --latest-npm >/dev/null 2>&1 || true
        nvm use "$node_version" >/dev/null 2>&1 || true
      fi
    fi
    nvm use >/dev/null 2>&1 || true
  fi

  if command -v node >/dev/null 2>&1; then
    node_bin_dir="$(dirname "$(command -v node)")"
    PATH="$node_bin_dir:$PATH"
    export PATH
  else
    say "Node.js is required. Install Node 20+ (or nvm) and retry."
    exit 1
  fi

  if ! command -v npm >/dev/null 2>&1; then
    say "npm is required. Ensure your Node installation includes npm."
    exit 1
  fi
}

start_backend() {
  say "Starting backend on $BACKEND_HOST:$BACKEND_PORT"
  (
    cd "$ROOT_DIR"
    SANKALP_HOST="$BACKEND_HOST" SANKALP_PORT="$BACKEND_PORT" nohup python3 server.py >>"$BACKEND_LOG" 2>&1 </dev/null &
    echo $! >"$BACKEND_PID_FILE"
  )
}

start_frontend() {
  say "Starting frontend on $FRONTEND_HOST:$FRONTEND_PORT"
  (
    nvm_dir="${NVM_DIR:-$HOME/.nvm}"
    nohup /bin/zsh -lc '
      set -eu
      if [ -s "'"$nvm_dir"'/nvm.sh" ]; then
        source "'"$nvm_dir"'/nvm.sh"
      fi
      cd "'"$ROOT_DIR"'/web"
      if command -v nvm >/dev/null 2>&1 && [ -f .nvmrc ]; then
        node_version="$(tr -d '"'"'[:space:]'"'"' < .nvmrc)"
        if [ -n "$node_version" ]; then
          nvm install "$node_version" --latest-npm >/dev/null 2>&1 || true
          nvm use "$node_version" >/dev/null 2>&1 || true
        fi
      fi
      if [ ! -x ./node_modules/.bin/vite ]; then
        npm install --no-fund --no-audit
      fi
      npm run dev -- --port "'"$FRONTEND_PORT"'"
    ' >>"$FRONTEND_LOG" 2>&1 </dev/null &
    echo $! >"$FRONTEND_PID_FILE"
  )
}

main() {
  need_tool python3
  ensure_node
  mkdir -p "$LOG_DIR"

  kill_by_pid_file "$BACKEND_PID_FILE"
  kill_by_pid_file "$FRONTEND_PID_FILE"
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"

  start_backend
  start_frontend

  if ! wait_for_port "$BACKEND_PORT" 20; then
    say "Backend failed to start on port $BACKEND_PORT. Check: $BACKEND_LOG"
    exit 1
  fi
  if ! wait_for_port "$FRONTEND_PORT" 40; then
    say "Frontend failed to start on port $FRONTEND_PORT. Check: $FRONTEND_LOG"
    exit 1
  fi

  say "Sankalp dev servers relaunched."
  say "Backend: http://$BACKEND_HOST:$BACKEND_PORT"
  say "Frontend: http://$FRONTEND_HOST:$FRONTEND_PORT"
  say "Logs: $BACKEND_LOG and $FRONTEND_LOG"
  open_frontend
}

main "$@"
