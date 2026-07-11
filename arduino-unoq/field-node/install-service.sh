#!/usr/bin/env bash
#
# Install (or update) the field-node so it starts automatically on every power-on.
# Run once, with sudo:
#
#     sudo ./install-service.sh
#
# It does two things:
#   1. makes the on-board LoRa modem sketch the boot-default Arduino App, so the MCU
#      side comes up on its own;
#   2. installs + enables the systemd service that runs the Linux gateway (run.sh).
#
# After this, "power on" == "everything running". Nothing else to launch by hand.
# Safe to re-run: it just refreshes the unit and restarts the service.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT="field-node.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "This installs a system service — run it with sudo:" >&2
  echo "    sudo $0" >&2
  exit 1
fi

# 0. Bluetooth: make BlueZ power the controller on its own at boot. Without this the
#    adapter comes up DOWN and the gateway's first BLE scan aborts with "No Bluetooth
#    adapters found". We let bluetoothd own the controller — we never poke it with
#    hciconfig/btmgmt, which can hang this board's UART HCI.
MAIN_CONF=/etc/bluetooth/main.conf
if [[ -f "$MAIN_CONF" ]] && ! grep -qE '^\s*AutoEnable\s*=\s*true' "$MAIN_CONF"; then
  echo "==> Enabling BlueZ AutoEnable (power the BT controller at boot)"
  if grep -qE '^\s*#?\s*AutoEnable\s*=' "$MAIN_CONF"; then
    sed -i -E 's|^\s*#?\s*AutoEnable\s*=.*|AutoEnable=true|' "$MAIN_CONF"
  else
    sed -i -E 's|^\s*\[Policy\]\s*$|[Policy]\nAutoEnable=true|' "$MAIN_CONF"
  fi
  systemctl restart bluetooth || true
fi

# 1. MCU side: the LoRa modem sketch auto-runs on boot (as the arduino user).
echo "==> Setting the LoRa modem (sankat) as the boot-default Arduino App"
sudo -u arduino arduino-app-cli properties set default /home/arduino/ArduinoApps/sankat

# 2. Linux side: the gateway service.
echo "==> Installing $UNIT"
install -m 644 "$HERE/$UNIT" "/etc/systemd/system/$UNIT"
systemctl daemon-reload
systemctl enable "$UNIT"
systemctl restart "$UNIT"

echo
echo "==> Done. Current status:"
systemctl --no-pager --full status "$UNIT" | head -n 15 || true
echo
echo "Watch it come up:   ./logs.sh"
echo "Stop it:            ./stop.sh"
