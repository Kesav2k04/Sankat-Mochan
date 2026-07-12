#!/usr/bin/env bash
#
# dev.sh — one-shot local launcher for the Sankat-Mochan command post (macOS).
#
# Frees the ports first (kills any stale process still holding them), then runs:
#   • backend  — FastAPI via uvicorn  → http://localhost:9000
#   • frontend — Vite dev server      → http://localhost:5173  (proxies API to :9000)
#
# Ctrl+C stops both cleanly.
#
# Usage:
#   ./dev.sh              # start backend + frontend
#   ./dev.sh backend      # start backend only
#   ./dev.sh frontend     # start frontend only
#
set -euo pipefail

# --- config -----------------------------------------------------------------
BACKEND_PORT=9000
FRONTEND_PORT=5173

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$SCRIPT_DIR/web"
VENV_DIR="$SCRIPT_DIR/.venv"

# --- helpers ----------------------------------------------------------------

# Free a TCP port on macOS: find any PID listening on it (lsof) and kill it.
free_port() {
  local port="$1"
  # -t: terse (PIDs only), -i: internet, -sTCP:LISTEN: only listeners.
  local pids
  pids="$(lsof -t -i "TCP:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "⚠️  Port ${port} in use by PID(s): ${pids//$'\n'/ } — killing…"
    # Try graceful first, then force if still alive.
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 1
    pids="$(lsof -t -i "TCP:${port}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      echo "   still up — force killing (SIGKILL)…"
      echo "$pids" | xargs kill -9 2>/dev/null || true
      sleep 1
    fi
    echo "✅ Port ${port} freed."
  else
    echo "✅ Port ${port} is free."
  fi
}

# Track child PIDs so we can clean up on exit.
PIDS=()
cleanup() {
  echo ""
  echo "🛑 Shutting down…"
  for pid in "${PIDS[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
  # Also sweep the ports in case a child spawned its own workers.
  free_port "$BACKEND_PORT" >/dev/null 2>&1 || true
  free_port "$FRONTEND_PORT" >/dev/null 2>&1 || true
  exit 0
}
trap cleanup INT TERM

start_backend() {
  free_port "$BACKEND_PORT"
  echo "🚀 Starting backend (uvicorn) on :${BACKEND_PORT}…"
  cd "$SCRIPT_DIR"
  # uv is the project standard: `uv run` syncs .venv from pyproject.toml on first use.
  # Fall back to an already-populated .venv, then system python3, if uv is missing.
  if command -v uv >/dev/null 2>&1; then
    uv run uvicorn app:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload &
  elif [[ -x "$VENV_DIR/bin/python" ]]; then
    echo "   (uv not found — using .venv; install uv: https://docs.astral.sh/uv/)"
    "$VENV_DIR/bin/python" -m uvicorn app:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload &
  else
    echo "   (neither uv nor .venv found — using system python3)"
    python3 -m uvicorn app:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload &
  fi
  PIDS+=($!)
}

start_frontend() {
  free_port "$FRONTEND_PORT"
  if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    echo "📦 Installing frontend deps (first run)…"
    ( cd "$WEB_DIR" && npm install )
  fi
  echo "🚀 Starting frontend (vite) on :${FRONTEND_PORT}…"
  ( cd "$WEB_DIR" && npm run dev -- --port "$FRONTEND_PORT" ) &
  PIDS+=($!)
}

# --- main -------------------------------------------------------------------
MODE="${1:-all}"
case "$MODE" in
  backend)  start_backend ;;
  frontend) start_frontend ;;
  all)      start_backend; start_frontend ;;
  *) echo "Usage: $0 [backend|frontend|all]"; exit 1 ;;
esac

echo ""
echo "─────────────────────────────────────────────"
echo "  backend : http://localhost:${BACKEND_PORT}"
[[ "$MODE" != "backend" ]] && echo "  frontend: http://localhost:${FRONTEND_PORT}"
echo "  Ctrl+C to stop."
echo "─────────────────────────────────────────────"

# Wait on all children; cleanup() runs on Ctrl+C.
wait
