#!/usr/bin/env bash
#
# Refresh arduino-uno-q/field-node/ from the source of truth in raspberrypi/.
#
# The UNO Q ships as a self-contained folder (only arduino-uno-q/ goes to the board), so
# it carries its own copy of the mesh code. raspberrypi/ stays canonical; run this after
# changing anything there to keep the two in step. config.json is deliberately NOT copied
# (it is the field board's own, preconfigured for the on-board bridge modem).
#
# Run from anywhere:  arduino-uno-q/sync-from-raspberrypi.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$HERE/../raspberrypi" && pwd)"
DST="$HERE/field-node"

FILES=(
  ble_link.py chainlog.py config.py envelope.py gateway.py gpio_compat.py
  node.py preflight.py run.sh serial_radio.py bridge_radio.py bridge_client.py
  sx127x.py uplink.py config.example.json pyproject.toml
)

mkdir -p "$DST"
for f in "${FILES[@]}"; do
  cp "$SRC/$f" "$DST/$f"
done
chmod +x "$DST/run.sh" "$DST/gateway.py" "$DST/preflight.py" 2>/dev/null || true

echo "synced ${#FILES[@]} files from raspberrypi/ -> field-node/  (config.json left as-is)"
