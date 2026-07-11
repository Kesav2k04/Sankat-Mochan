#!/usr/bin/env bash
#
# Sankat-Mochan backend, one command.
#
#   ./server.sh              radios here, command post on the Mac (the normal case)
#   ./server.sh local        command post + LoRa gateway, both on this machine
#   ./server.sh post         command post only (no radios, no Bluetooth)
#   ./server.sh --post URL   override where the command post lives
#   ./server.sh --port 8000  serve the *local* post on a different port
#
# The command post is a FastAPI app (command-post/app.py) served by uvicorn. The gateway
# is pi-code/run.sh, which does its own pre-flight on the radios.
#
# Supervision: if either process dies it is restarted, with backoff, for as long as this
# script runs. Ctrl-C stops both cleanly. Each child's output is tee'd to logs/.
set -uo pipefail
shopt -s extglob

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
POST_DIR="$ROOT/command-post"
LOG_DIR="$ROOT/logs"
PORT="${PORT:-9000}"
HOST="${HOST:-0.0.0.0}"

HEALTHY_AFTER_S=15   # a child that lives this long counts as "started"
MAX_FAST_FAILURES=3

# --- where the command post lives -------------------------------------------
# Tried in order; the first concrete address answering /health wins. A Mac can publish
# loopback, VM and VPN addresses under the same .local name, so pick_post resolves the
# name and probes each IPv4 address instead of handing the ambiguous hostname to the
# long-lived WebSocket. The raw IP remains a fallback when venue Wi-Fi blocks mDNS.
#
# Override without editing this file:  ./server.sh --post http://host:9000
#                                      SANKAT_POST=http://host:9000 ./server.sh
# These are plain LAN addresses — no credentials belong in a URL (rule 2).
DEFAULT_POST="http://QCWorkshop.local:9000,http://10.83.166.221:9000"

MODE="gateway"                       # radios here, post on the Mac
POST_CANDIDATES="${SANKAT_POST:-$DEFAULT_POST}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    post)     MODE="post";    shift ;;
    gateway)  MODE="gateway"; shift ;;
    local|all) MODE="local";  shift ;;   # both halves on this machine
    --port) PORT="$2"; shift 2 ;;
    --post) POST_CANDIDATES="$2"; shift 2 ;;
    -h|--help) sed -n '3,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1 (try --help)" >&2; exit 2 ;;
  esac
done

# "local" means the post is here, so ignore whatever remote address is configured.
[[ "$MODE" == "local" ]] && POST_CANDIDATES=""

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
MAIN_PID=$$

# TERM a child and everything it spawned; SIGKILL whatever ignores it.
stop_tree() {
  local pid="${1:-}"
  [[ -n "$pid" ]] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.3
  done
  kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
}

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
    stop_tree "$(cat "$f")"
    rm -f "$f"
  done
  wait 2>/dev/null || true
  echo "stopped."
}
trap cleanup INT TERM EXIT

# --- live log formatting ---------------------------------------------------
# Colour only when someone is actually watching; a redirected log full of escape
# codes is worse than no colour. NO_COLOR=1 disables it outright.
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_RESET=$'\033[0m'; C_DIM=$'\033[2m'; C_RED=$'\033[31m'
  C_YEL=$'\033[33m';  C_GRN=$'\033[32m'; C_CYN=$'\033[36m'; C_BOLD=$'\033[1m'
else
  C_RESET=""; C_DIM=""; C_RED=""; C_YEL=""; C_GRN=""; C_CYN=""; C_BOLD=""
fi

# Read a child's output line by line: tag it, colour it by severity, echo it to the
# terminal, and append the *uncoloured* line to its log file.
prefix_stream() {
  local name="$1" tag_colour="$2" logfile="$3" line colour now shown
  while IFS= read -r line; do
    printf '%s\n' "$line" >>"$logfile"          # the file keeps the raw line
    [[ -z "${line//[[:space:]]/}" ]] && continue  # blank lines help nobody

    shown="$line"
    # uvicorn pads every line with "INFO:" then a run of spaces. The severity is already
    # carried by the colour, and the padding wrecks the alignment of everything else.
    case "$shown" in
      INFO:*)  shown="${shown#INFO:}"; shown="${shown##+([[:space:]])}" ;;
    esac
    # The gateway already stamps HH:MM:SS. Only stamp what does not.
    if [[ ! "$shown" =~ ^[0-9]{2}:[0-9]{2}:[0-9]{2} ]]; then
      printf -v now '%(%H:%M:%S)T' -1     # bash builtin: no fork per line
      shown="$now $shown"
    fi

    case "$line" in
      *ERROR*|*FAIL*|*Traceback*|*error:*)   colour="$C_RED" ;;
      *WARNING*|*WARN*)                      colour="$C_YEL" ;;
      *PASSED*|*READY*|*connected*|*" OK"*)  colour="$C_GRN" ;;
      *DEBUG*)                               colour="$C_DIM" ;;
      *)                                     colour="" ;;
    esac
    printf '%s%s%s %s%s%s\n' "$tag_colour" "[$name]" "$C_RESET" "$colour" "$shown" "$C_RESET"
  done
}

# supervise <name> <logfile> <workdir> <colour> <command...>
# Restarts the command whenever it exits non-zero, for as long as this script runs.
# Backs off, so a process that dies instantly cannot spin the CPU.
supervise() {
  local name="$1" logfile="$2" workdir="$3" tag_colour="$4"; shift 4
  local child="" napper="" delay=1 fast_failures=0 launches=0
  # Propagate a stop to whatever we are currently waiting on, then leave.
  trap 'stop_tree "$child"; kill -TERM "$napper" 2>/dev/null; rm -f "$LOG_DIR/$name.child.pid"; exit 0' TERM INT
  while true; do
    # Only announce a *re*start; the first launch is implied by the banner above.
    (( launches++ ))
    if (( launches > 1 )); then
      printf '%s%s%s %srestarting…%s\n' "$tag_colour" "[$name]" "$C_RESET" "$C_YEL" "$C_RESET"
    fi
    echo "[$name] starting: $*" >>"$logfile"
    local began=$SECONDS
    # setsid puts the child in a new process group, so `kill -- -$child` reaches its
    # whole tree. run.sh is a bash wrapper around gateway.py; killing only the wrapper
    # orphans gateway.py, which then keeps the radios busy and blocks the next start.
    ( cd "$workdir" && exec setsid "$@" ) \
        > >(prefix_stream "$name" "$tag_colour" "$logfile") 2>&1 &
    child=$!
    echo "$child" > "$LOG_DIR/$name.child.pid"

    # If server.sh is SIGKILLed it cannot run its trap, and this supervisor would sit in
    # `wait` forever with a live child holding the radios — which is exactly what makes
    # the *next* run fail pre-flight with "GPIO busy". Watch the parent from the side.
    ( while kill -0 "$MAIN_PID" 2>/dev/null; do sleep 2; done
      kill -TERM -- "-$child" 2>/dev/null || kill -TERM "$child" 2>/dev/null ) &
    local orphan_watch=$!

    wait "$child"; local rc=$?
    kill -TERM "$orphan_watch" 2>/dev/null
    rm -f "$LOG_DIR/$name.child.pid"
    # If server.sh was SIGKILLed we cannot be told to stop, and restarting forever would
    # leave an orphan holding the port. Check the parent is still there.
    if ! kill -0 "$MAIN_PID" 2>/dev/null; then
      echo "[$name] parent is gone — exiting" >>"$logfile"
      exit 0
    fi
    if [[ $rc -eq 0 ]]; then
      printf '%s%s%s %sexited cleanly%s\n' "$tag_colour" "[$name]" "$C_RESET" "$C_GRN" "$C_RESET"
      echo "[$name] exited cleanly" >>"$logfile"
      return 0
    fi

    # Restarting is for a process that crashed after doing some work. A process that dies
    # immediately, over and over, has a permanent problem — bad wiring, a busy radio, a
    # port in use — and looping just buries the error message under restart noise.
    if (( SECONDS - began < HEALTHY_AFTER_S )); then
      (( fast_failures++ ))
    else
      fast_failures=0
    fi
    if (( fast_failures >= MAX_FAST_FAILURES )); then
      printf '%s[%s]%s %sfailed %d times in a row without staying up. This will not fix itself.%s\n' \
        "$tag_colour" "$name" "$C_RESET" "$C_RED" "$fast_failures" "$C_RESET"
      printf '  the last error is above, and in %s\n' "$logfile"
      echo "[$name] gave up after $fast_failures fast failures" >>"$logfile"
      kill -TERM "$MAIN_PID" 2>/dev/null
      return 1
    fi

    printf '%s[%s]%s %sexited with status %d — restarting in %ds%s\n' \
      "$tag_colour" "$name" "$C_RESET" "$C_YEL" "$rc" "$delay" "$C_RESET"
    echo "[$name] exited with status $rc — restarting in ${delay}s" >>"$logfile"
    # `sleep $delay` would swallow Ctrl-C for up to 30s: bash defers a trap until the
    # foreground command finishes. Backgrounding it makes the wait interruptible.
    sleep "$delay" & napper=$!
    wait "$napper" 2>/dev/null
    delay=$(( delay < 30 ? delay * 2 : 30 ))
  done
}

# A port already in use is the difference between "the server restarted" and "you are
# talking to a stale process from the last run". Fail loudly instead.
port_in_use() {
  ss -lntH "sport = :$1" 2>/dev/null | grep -q .
}

# Two gateways cannot share one pair of radios: the second one's pre-flight reports
# "GPIO busy" and exits, forever. Name the culprit instead of restart-looping on it.
radios_busy() {
  pgrep -f "pi-code/gateway\.py" >/dev/null 2>&1
}

# Echo the first base URL whose /health answers. Nothing on stdout means none did.
pick_post() {
  local input="$1" base scheme host port address route
  local -a bases addresses direct routed
  IFS=, read -r -a bases <<<"$input"

  for base in "${bases[@]}"; do
    base="${base%/}"
    if [[ ! "$base" =~ ^(https?)://([^/:]+)(:([0-9]+))?$ ]]; then
      echo "  ignoring invalid command-post address: $base" >&2
      continue
    fi
    scheme="${BASH_REMATCH[1]}"
    host="${BASH_REMATCH[2]}"
    if [[ -n "${BASH_REMATCH[4]}" ]]; then
      port="${BASH_REMATCH[4]}"
    elif [[ "$scheme" == https ]]; then
      port=443
    else
      port=80
    fi

    # Resolve through the Pi's normal NSS stack (including Avahi for .local). Ignore
    # loopback/link-local answers: they identify this Pi, never the remote Mac. Python
    # is already guaranteed above and ipaddress/socket are stdlib.
    addresses=()
    while IFS= read -r address; do
      [[ -n "$address" ]] && addresses+=("$address")
    done < <("$PY" - "$host" <<'PY'
import ipaddress
import socket
import sys

host = sys.argv[1]
try:
    infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
except OSError:
    infos = []
seen = set()
for info in infos:
    address = info[4][0]
    ip = ipaddress.ip_address(address)
    if address not in seen and not (ip.is_loopback or ip.is_link_local or ip.is_unspecified):
        seen.add(address)
        print(address)
PY
    )

    # Try same-LAN addresses before anything routed through a gateway. This avoids a
    # Mac VM/VPN address consuming the timeout ahead of its real Wi-Fi/Ethernet IP.
    direct=(); routed=()
    for address in "${addresses[@]}"; do
      route="$(ip -4 route get "$address" 2>/dev/null || true)"
      if [[ -n "$route" && "$route" != *" via "* ]]; then
        direct+=("$address")
      else
        routed+=("$address")
      fi
    done

    for address in "${direct[@]}" "${routed[@]}"; do
      [[ -n "$address" ]] || continue
      if curl -fsS --noproxy '*' -o /dev/null --connect-timeout 2 --max-time 3 \
          "$scheme://$address:$port/health" 2>/dev/null; then
        echo "$scheme://$address:$port"
        return 0
      fi
      echo "  no answer from $scheme://$address:$port/health ($host)" >&2
    done

    # Some minimal images resolve .local inside curl but not Python/NSS. Keep this
    # compatibility attempt last; successful named endpoints are still better than no
    # uplink, and the explicit raw-IP fallback is tried next if it fails.
    if (( ${#addresses[@]} == 0 )) && \
       curl -fsS --noproxy '*' -o /dev/null --connect-timeout 2 --max-time 3 \
         "$base/health" 2>/dev/null; then
      echo "$base"
      return 0
    fi
    (( ${#addresses[@]} > 0 )) || echo "  could not resolve $host" >&2
  done
  return 1
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
if [[ "$MODE" == "post" || "$MODE" == "local" ]]; then
  step "Command post (FastAPI)"
  if port_in_use "$PORT"; then
    die "port $PORT is already in use — an old server is still running.
  find it:  ss -lptn 'sport = :$PORT'
  or serve elsewhere:  ./server.sh $MODE --port 9100"
  fi
  echo "  http://$HOST:$PORT/   ·   ws://$HOST:$PORT/gateway"
  supervise post "$LOG_DIR/command-post.log" "$POST_DIR" "$C_CYN" \
    "$VENV/bin/uvicorn" app:app --host "$HOST" --port "$PORT" &
  SUPERVISORS+=($!)

  wait_for_health || die "the command post never became healthy — see $LOG_DIR/command-post.log"
fi

if [[ "$MODE" == "gateway" || "$MODE" == "local" ]]; then
  step "LoRa gateway"

  # Where does this gateway send accepted envelopes?
  if [[ -n "$POST_CANDIDATES" ]]; then
    echo "  looking for a command post: $POST_CANDIDATES"
    POST_BASE="$(pick_post "$POST_CANDIDATES")" || die "none of those command posts answered /health.
  Is uvicorn running there, and is the port open through its firewall?
    on the Mac:  cd command-post && uvicorn app:app --host 0.0.0.0 --port 9000
    from here:   curl http://<mac>:9000/health"
    echo "  using $POST_BASE"
  elif [[ "$MODE" == "local" ]]; then
    POST_BASE="http://127.0.0.1:$PORT"
    echo "  local mode: uplinking to the command post this script just started"
  else
    POST_BASE=""
  fi
  if radios_busy; then
    die "another gateway already holds the radios:
$(pgrep -af "pi-code/gateway\.py" | sed 's/^/    /')
  stop it first:  kill $(pgrep -f "pi-code/gateway\.py" | tr '\n' ' ')"
  fi
  # Point the gateway's durable uplink at whichever post we found. No secret belongs
  # in a URL (rule 2); these are plain LAN addresses.
  if [[ -n "$POST_BASE" ]]; then
    export SANKAT_UPLINK__ENABLED=true
    export SANKAT_UPLINK__URL="$POST_BASE/sos"
    echo "  uplink -> $SANKAT_UPLINK__URL"
  else
    echo "  no command post given — running the mesh without an uplink"
    echo "  (add --post http://<mac>:9000 to stream envelopes to the dashboard)"
  fi
  supervise gateway "$LOG_DIR/gateway.log" "$ROOT/pi-code" "$C_GRN" "$ROOT/pi-code/run.sh" &
  SUPERVISORS+=($!)
fi

echo
printf '%s%s%s\n' "$C_BOLD" "────────────────────────────────────────────────────────────" "$C_RESET"
printf '%s  Sankat-Mochan is running.  Ctrl-C stops everything.%s\n' "$C_BOLD" "$C_RESET"
case "$MODE" in
  post)    printf '  command post   %s\n' "http://$HOST:$PORT/" ;;
  gateway) printf '  radios         field + gateway on 433 MHz\n'
           [[ -n "$POST_BASE" ]] && printf '  command post   %s\n' "$POST_BASE" ;;
  local)   printf '  command post   %s\n' "http://$HOST:$PORT/"
           printf '  radios         field + gateway on 433 MHz\n' ;;
esac
printf '  logs           %s/\n' "$LOG_DIR"
printf '  audit the air  %s\n' "$ROOT/pi-code/run.sh proof"
printf '%s%s%s\n\n' "$C_BOLD" "────────────────────────────────────────────────────────────" "$C_RESET"
wait
