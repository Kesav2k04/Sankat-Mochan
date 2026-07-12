#!/usr/bin/env bash
#
# Stop the field-node now. This is a manual stop only — it does NOT disable
# auto-start, so the next power-on (or reboot) brings everything back up.
#
#     ./stop.sh          stop the Linux gateway (needs sudo for systemctl)
#     ./stop.sh all      also stop the on-board LoRa modem app on the MCU
#
# To permanently stop auto-starting on boot, use:  sudo systemctl disable field-node

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Stopping the field-node gateway..."
sudo systemctl stop field-node.service

if [[ "${1:-}" == "all" ]]; then
  echo "Stopping the on-board LoRa modem app..."
  arduino-app-cli app stop "$HERE/../.." 2>/dev/null \
    || arduino-app-cli app stop /home/arduino/ArduinoApps/sankat 2>/dev/null \
    || echo "  (modem app was not running)"
fi

echo "Stopped. It will start again on the next power-on."
