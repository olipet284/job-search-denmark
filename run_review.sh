#!/usr/bin/env bash
# Lightweight launcher for the Job Review UI
# - Activates venv if present
# - Starts Flask app on chosen port
# - Opens default browser
# Usage:
#   ./run_review.sh                         # start server on an auto-selected free port
#   ./run_review.sh start [PORT]            # start server (default 8010 if omitted; auto if omitted entirely)
#   ./run_review.sh stop [PORT]             # stop server on port (default 8010)
#   ./run_review.sh status [PORT]           # show status
# Legacy: ./run_review.sh [PORT] still starts the server.
# NOTE: Dependencies are no longer installed automatically for faster startup.
#       Run ./install.sh once (or after changing requirements) before using this script.
set -euo pipefail
CMD="start"
IDLE_TIMEOUT=""   # (deprecated) retained for compatibility; no effect
PORT="8010"           # default if user explicitly supplies no numeric but we won't use it if auto-picking
USER_PORT_SET=0        # flag if user provided a numeric port
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
VENV_DIR="${PROJECT_ROOT}/../.venv"
PY="python3"
REQ_FILE="${PROJECT_ROOT}/requirements.txt"

# Parse args (simple)
ARGS=()
for a in "$@"; do
  case "$a" in
    start|stop|status) CMD="$a" ;;
    --idle|--idle=*|--idle*) echo "[warn] --idle flag deprecated and ignored" >&2 ;;
  [0-9]*) PORT="$a"; USER_PORT_SET=1 ;;
    *) ARGS+=("$a") ;;
  esac
done

PID_FILE="${SCRIPT_DIR}/.review_app.pid"
PORT_FILE="${SCRIPT_DIR}/.review_app.port"

is_running() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

load_pid() {
  [ -f "$PID_FILE" ] && cat "$PID_FILE" || true
}

stop_server() {
  local pid="$(load_pid)"
  # attempt to load port (for message only)
  if [ -f "$PORT_FILE" ]; then PORT="$(cat "$PORT_FILE" 2>/dev/null || echo "$PORT")"; fi
  if is_running "$pid"; then
    echo "[stop] Sending SIGTERM to PID $pid" >&2
    kill "$pid" 2>/dev/null || true
    for i in {1..20}; do
      if ! is_running "$pid"; then echo "[stop] Stopped." >&2; rm -f "$PID_FILE"; return 0; fi
      sleep 0.2
    done
    echo "[stop] Forcing SIGKILL" >&2
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
  else
    echo "[stop] No running server (stale pid file?)" >&2
    rm -f "$PID_FILE" 2>/dev/null || true
  fi
}

show_status() {
  local pid="$(load_pid)"
  if [ -f "$PORT_FILE" ]; then PORT="$(cat "$PORT_FILE" 2>/dev/null || echo "$PORT")"; fi
  if is_running "$pid"; then
    echo "[status] Running (PID $pid) on port $PORT" >&2
    exit 0
  else
    echo "[status] Not running" >&2
    exit 1
  fi
}

if [ "$CMD" = "stop" ]; then
  stop_server; exit 0
elif [ "$CMD" = "status" ]; then
  show_status; fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "[error] Virtual environment not found: ${VENV_DIR}" >&2
  echo "        Run ./install.sh first." >&2
  exit 1
fi
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
PY="${VENV_DIR}/bin/python"

# Fast pre-flight: verify flask import only (no installs). Quote $PY due to spaces in path.
echo "[debug] Using interpreter: $PY" >&2
if ! "$PY" -c 'import flask'; then
  echo "[error] Flask not installed in venv (import failed). Run ./install.sh" >&2
  exit 1
fi

# Auto-pick a free port if user did not specify one AND no explicit numeric arg AND command is start
if [ "$CMD" = "start" ] && [ $USER_PORT_SET -eq 0 ] && [ $# -eq 0 ]; then
  PORT="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); p=s.getsockname()[1]; s.close(); print(p)')"
  echo "[auto] Selected free port $PORT" >&2
fi

HOST="127.0.0.1"
URL="http://${HOST}:${PORT}"

# If something already running, report and exit
if [ -f "$PID_FILE" ]; then
  existing_pid=$(load_pid)
  if is_running "$existing_pid"; then
    echo "[start] Server already running (PID $existing_pid). Use: $0 stop" >&2
    exit 0
  fi
  rm -f "$PID_FILE"
fi

# No idle timeout env exported (feature removed)

"${PY}" "${SCRIPT_DIR}/review_app.py" --host "${HOST}" --port "${PORT}" --no-open &
APP_PID=$!
echo ${APP_PID} > "$PID_FILE"
echo ${PORT} > "$PORT_FILE"
echo "[start] PID $APP_PID (port $PORT)" >&2
sleep 1
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 &
elif command -v sensible-browser >/dev/null 2>&1; then
  sensible-browser "$URL" &
else
  echo "Open $URL in your browser." >&2
fi

# Idle timeout now handled internally by backend when REVIEW_APP_IDLE_TIMEOUT is set.

trap 'echo "[trap] Stopping review app (PID ${APP_PID})"; kill ${APP_PID} 2>/dev/null || true' INT TERM EXIT
wait ${APP_PID} 2>/dev/null || true
rm -f "$PID_FILE" 2>/dev/null || true
