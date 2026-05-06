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

ensure_node() {
  if command -v node >/dev/null 2>&1; then
    return
  fi
  if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
    # shellcheck disable=SC1090
    . "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
  fi
  if command -v nvm >/dev/null 2>&1; then
    nvm use >/dev/null 2>&1 || true
  fi
  command -v node >/dev/null 2>&1 || {
    say "Node.js is required. Install Node 20+ (or nvm) and retry."
    exit 1
  }
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
    cd "$ROOT_DIR/web"
    nohup npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" >>"$FRONTEND_LOG" 2>&1 </dev/null &
    echo $! >"$FRONTEND_PID_FILE"
  )
}

main() {
  need_tool python3
  need_tool npm
  ensure_node
  mkdir -p "$LOG_DIR"

  kill_by_pid_file "$BACKEND_PID_FILE"
  kill_by_pid_file "$FRONTEND_PID_FILE"
  kill_port "$BACKEND_PORT"
  kill_port "$FRONTEND_PORT"

  start_backend
  start_frontend

  say "Sankalp dev servers relaunched."
  say "Backend: http://$BACKEND_HOST:$BACKEND_PORT"
  say "Frontend: http://$FRONTEND_HOST:$FRONTEND_PORT"
  say "Logs: $BACKEND_LOG and $FRONTEND_LOG"
}

main "$@"
