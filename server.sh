#!/usr/bin/env bash
#
# Sankat-Mochan backend, one command.
#
#   ./server.sh              command post + LoRa gateway, supervised
#   ./server.sh post         command post only (no radios, no Bluetooth)
#   ./server.sh gateway      LoRa gateway only (talks to an already-running post)
#   ./server.sh --port 8000  serve on a different port
#
# The command post is a FastAPI app (command-post/app.py) served by uvicorn. The gateway
# is pi-code/run.sh, which does its own pre-flight on the radios.
#
# Supervision: if either process dies it is restarted, with backoff, for as long as this
# script runs. Ctrl-C stops both cleanly. Each child's output is tee'd to logs/.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
POST_DIR="$ROOT/command-post"
LOG_DIR="$ROOT/logs"
PORT="${PORT:-9000}"
HOST="${HOST:-0.0.0.0}"

MODE="all"
while [[ $# -gt 0 ]]; do
  case "$1" in
    post|gateway|all) MODE="$1"; shift ;;
    --port) PORT="$2"; shift 2 ;;
    -h|--help) sed -n '3,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR"
step() { printf '\n==> %s\n' "$*"; }
die()  { printf '\nerror: %s\n' "$*" >&2; exit 1; }

# --- 1. Python environment -------------------------------------------------
# --system-site-packages so the distro's spidev + RPi.GPIO stay visible, exactly as
# pi-code/run.sh expects. Both scripts share this one venv on purpose.
step "Python environment"
if [[ ! -x "$PY" ]]; then
  echo "  creating venv at $VENV"
  python3 -m venv --system-site-packages "$VENV" || die "could not create the venv"
fi

# Only reinstall when requirements actually change — a pip run per boot is slow on a Pi.
REQ="$POST_DIR/requirements.txt"
STAMP="$VENV/.requirements.sha"
if [[ ! -f "$STAMP" ]] || ! sha256sum -c --status "$STAMP" 2>/dev/null; then
  echo "  installing command-post requirements (first run, or they changed)"
  "$PY" -m pip install --quiet --upgrade pip || die "pip self-upgrade failed"
  "$PY" -m pip install --quiet -r "$REQ" || die "could not install $REQ"
  sha256sum "$REQ" > "$STAMP"
else
  echo "  requirements already satisfied"
fi
"$PY" - <<'EOF' || die "the command post's imports are not satisfied"
import importlib, sys
missing = [m for m in ("fastapi", "uvicorn", "numpy", "soundfile", "websockets")
           if not importlib.util.find_spec(m)]
if missing:
    print("  missing modules:", ", ".join(missing), file=sys.stderr)
    sys.exit(1)
print("  imports OK: fastapi, uvicorn, numpy, soundfile, websockets")
EOF

# --- 2. Child processes ----------------------------------------------------
# Each service gets a supervisor (a background subshell that restarts it) and each
# supervisor records its current child's pid in a file. Shutdown needs both: killing the
# supervisor alone leaves uvicorn running, and killing the child alone makes the
# supervisor restart it.
SUPERVISORS=()

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "==> stopping"
  # Supervisors first, so nothing gets restarted underneath us.
  for pid in "${SUPERVISORS[@]:-}"; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  for f in "$LOG_DIR"/*.child.pid; do
    [[ -f "$f" ]] || continue
    kill -TERM "$(cat "$f")" 2>/dev/null || true
    rm -f "$f"
  done
  wait 2>/dev/null || true
  echo "stopped."
}
trap cleanup INT TERM EXIT

# supervise <name> <logfile> <workdir> <command...>
# Restarts the command whenever it exits non-zero, for as long as this script runs.
# Backs off, so a process that dies instantly cannot spin the CPU.
supervise() {
  local name="$1" logfile="$2" workdir="$3"; shift 3
  local child="" delay=1
  # Propagate a stop to the child, then leave.
  trap 'kill -TERM "$child" 2>/dev/null || true; exit 0' TERM INT
  while true; do
    echo "[$name] starting: $*" >>"$logfile"
    ( cd "$workdir" && exec "$@" ) >>"$logfile" 2>&1 &
    child=$!
    echo "$child" > "$LOG_DIR/$name.child.pid"
    wait "$child"; local rc=$?
    rm -f "$LOG_DIR/$name.child.pid"
    if [[ $rc -eq 0 ]]; then
      echo "[$name] exited cleanly" | tee -a "$logfile"
      return 0
    fi
    echo "[$name] exited with status $rc — restarting in ${delay}s" | tee -a "$logfile"
    sleep "$delay"
    delay=$(( delay < 30 ? delay * 2 : 30 ))
  done
}

wait_for_health() {
  local url="http://127.0.0.1:$PORT/health"
  for _ in $(seq 1 40); do
    if curl -fsS -o /dev/null --max-time 1 "$url" 2>/dev/null; then
      echo "  command post is up: $url"
      return 0
    fi
    sleep 0.5
  done
  return 1
}

# --- 3. Go -----------------------------------------------------------------
if [[ "$MODE" == "post" || "$MODE" == "all" ]]; then
  step "Command post (FastAPI)"
  echo "  http://$HOST:$PORT/   ·   ws://$HOST:$PORT/gateway"
  supervise post "$LOG_DIR/command-post.log" "$POST_DIR" \
    "$VENV/bin/uvicorn" app:app --host "$HOST" --port "$PORT" &
  SUPERVISORS+=($!)

  wait_for_health || die "the command post never became healthy — see $LOG_DIR/command-post.log"
fi

if [[ "$MODE" == "gateway" || "$MODE" == "all" ]]; then
  step "LoRa gateway"
  # Point the gateway's durable uplink at the post. Loopback, so nothing crosses a
  # network and no secret belongs here (rule 2).
  export SANKAT_UPLINK__ENABLED=true
  export SANKAT_UPLINK__URL="http://127.0.0.1:$PORT/sos"
  echo "  uplink -> $SANKAT_UPLINK__URL"
  supervise gateway "$LOG_DIR/gateway.log" "$ROOT/pi-code" "$ROOT/pi-code/run.sh" &
  SUPERVISORS+=($!)
fi

echo
echo "Running. Ctrl-C stops everything.   logs: $LOG_DIR/"
wait
