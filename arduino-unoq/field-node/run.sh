#!/usr/bin/env bash
#
# Sankat-Mochan LoRa gateway — one command to check, run, and verify.
#
#   ./run.sh            check everything, then run the gateway (waits for phones)
#   ./run.sh check      pre-flight only: config, deps, SPI, Bluetooth, both radios
#   ./run.sh test       pre-flight + full hardware self-test (8 scenarios, no phones)
#   ./run.sh radios     run the LoRa tier alone, no BLE, no phones needed
#   ./run.sh proof      print the chain log: did each envelope really cross the air?
#   ./run.sh logs       tail the human-readable log
#
# Safe to re-run. Creates the venv and installs deps on first use.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$(dirname "$HERE")/.venv"
PY="$VENV/bin/python"
MODE="${1:-run}"

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; RED=""; YELLOW=""; RESET=""
fi

step() { printf '\n%s==> %s%s\n' "$BOLD" "$1" "$RESET"; }
die()  { printf '%serror:%s %s\n' "$RED" "$RESET" "$1" >&2; exit 1; }
warn() { printf '%swarning:%s %s\n' "$YELLOW" "$RESET" "$1"; }

# Validate the mode before doing any work, so a typo can't sit through pre-flight.
case "$MODE" in
  run|check|test|radios|proof|logs|-h|--help|help) ;;
  *) die "unknown mode '$MODE' — try: ./run.sh help" ;;
esac

case "$MODE" in
  -h|--help|help)
    sed -n '3,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  proof)
    # Reads a log file; needs no radios, no Bluetooth. Use the venv python if present,
    # else the system python3 (chainlog.py is stdlib-only).
    PROOF_PY="$VENV/bin/python"; [[ -x "$PROOF_PY" ]] || PROOF_PY="$(command -v python3)"
    exec "$PROOF_PY" "$HERE/chainlog.py"
    ;;
  logs)
    [[ -f "$HERE/logs/gateway.log" ]] || die "no log yet — run ./run.sh test first"
    exec tail -f "$HERE/logs/gateway.log"
    ;;
  radios)
    # The LoRa tier alone. Tell pre-flight too, so a blocked adapter can't stop us.
    export SANKAT_BLE__ENABLED=false
    ;;
esac

# --- 1. Python environment -------------------------------------------------
# Prefer an isolated venv (the Pi), but the UNO Q ships without python3-venv, so fall back
# to the system python3 and install into it with pip. SANKAT_SYSTEM_PYTHON=1 forces that.
step "Python environment"
USING_VENV=0
if [[ "${SANKAT_SYSTEM_PYTHON:-0}" == "1" ]]; then
  PY="$(command -v python3 || true)"
  echo "  SANKAT_SYSTEM_PYTHON=1 — using the system python: $PY"
elif [[ -x "$PY" ]]; then
  USING_VENV=1
else
  echo "creating venv at $VENV"
  # --system-site-packages so the distro's spidev + RPi.GPIO (both MIT) are visible.
  if python3 -m venv --system-site-packages "$VENV" 2>/dev/null; then
    USING_VENV=1
  else
    warn "no python3-venv on this board — using the system python3 instead"
    PY="$(command -v python3 || true)"
  fi
fi
[[ -x "$PY" ]] || die "no usable python3 found on this board"

# Install bleak + requests + pyserial (all permissive-licensed) if missing. Into a venv
# this is trivial; into a Debian system python (PEP 668 'externally managed') we install
# under ~/.local via --user, adding --break-system-packages if the distro insists. spidev +
# RPi.GPIO are never pip-installed — on the Pi they come from the system packages, and a
# serial/field board does not need them.
pip_into_py() {
  if (( USING_VENV )); then
    "$PY" -m pip install --quiet "$@"
  else
    "$PY" -m pip install --quiet --user "$@" 2>/dev/null \
      || "$PY" -m pip install --quiet --user --break-system-packages "$@"
  fi
}
if ! "$PY" -c 'import bleak, requests, serial, msgpack' >/dev/null 2>&1; then
  echo "installing dependencies (bleak, requests, pyserial, msgpack)"
  (( USING_VENV )) && "$PY" -m pip install --quiet --upgrade pip >/dev/null 2>&1
  pip_into_py bleak requests pyserial msgpack || die "pip install failed. Try it directly:
  python3 -m pip install --user --break-system-packages bleak requests pyserial msgpack
  (is there network access on this board?)"
fi
echo "  $("$PY" -V) at $PY"

# --- 2. Bluetooth ----------------------------------------------------------
# The Pi's adapter comes up soft-blocked from cold; rfkill state does not reliably
# survive a reboot. Unblock it here so `bleak` doesn't fail with a confusing error.
if [[ "$MODE" != "radios" && "$MODE" != "proof" && "$MODE" != "logs" ]]; then
  step "Bluetooth adapter"
  if rfkill list bluetooth 2>/dev/null | grep -q "Soft blocked: yes"; then
    echo "adapter is soft-blocked, unblocking (needs sudo)"
    sudo rfkill unblock bluetooth || die "could not unblock bluetooth"
  fi
  sudo hciconfig hci0 up 2>/dev/null || true
  if rfkill list bluetooth 2>/dev/null | grep -q "Soft blocked: no"; then
    echo "  hci0 unblocked"
  else
    warn "bluetooth still blocked — 'run.sh radios' works without it"
  fi
fi

# --- 3. Pre-flight ---------------------------------------------------------
step "Pre-flight checks"
"$PY" "$HERE/preflight.py" || die "pre-flight failed — fix the items above, then re-run"

# --- 4. Dispatch -----------------------------------------------------------
case "$MODE" in
  check)
    printf '\n%sReady.%s Run "./run.sh test" for the full hardware self-test.\n' "$GREEN" "$RESET"
    ;;

  test)
    step "Hardware self-test (transmits — antennas must be attached)"
    "$PY" "$HERE/selftest_lora.py" || die "self-test failed"
    printf '\n%sAll good.%s\n' "$GREEN" "$RESET"
    ;;

  radios)
    step "Gateway, LoRa tier only (no BLE, no phones)"
    "$PY" "$HERE/gateway.py"      # SANKAT_BLE__ENABLED=false exported above
    ;;

  run)
    step "Starting gateway"
    echo "The gateway will:"
    echo "  1. probe the RF link (radio A -> radio B) and refuse to start if it fails"
    echo "  2. wait for any phone running the mesh app (Ctrl-C to stop)"
    echo "  3. accept SOS immediately and keep scanning for later responders"
    echo
    echo "Afterwards, verify with:  ./run.sh proof"
    echo
    "$PY" "$HERE/gateway.py"
    rc=$?
    case "$rc" in
      0)   printf '\n%sClean shutdown.%s\n' "$GREEN" "$RESET" ;;
      3)   die "the RF link is down — see the startup-probe hint above" ;;
      130) printf '\ninterrupted\n' ;;
      *)   die "gateway exited with status $rc" ;;
    esac
    ;;
esac
