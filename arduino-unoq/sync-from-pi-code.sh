#!/usr/bin/env bash
#
# Refresh arduino-unoq/field-node/ from the source of truth in pi-code/.
#
# The UNO Q ships as a self-contained folder (only arduino-unoq/ goes to the board), so
# it carries its own copy of the mesh code. pi-code/ stays canonical; run this after
# changing anything there to keep the two in step. config.json is deliberately NOT copied
# (it is the field board's own, preconfigured for the serial modem).
#
# Run from anywhere:  arduino-unoq/sync-from-pi-code.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$HERE/../pi-code" && pwd)"
DST="$HERE/field-node"

FILES=(
  ble_link.py chainlog.py config.py envelope.py gateway.py gpio_compat.py
  node.py preflight.py run.sh serial_radio.py sx127x.py uplink.py
  config.example.json
)

mkdir -p "$DST"
for f in "${FILES[@]}"; do
  cp "$SRC/$f" "$DST/$f"
done
chmod +x "$DST/run.sh" "$DST/gateway.py" "$DST/preflight.py" 2>/dev/null || true

echo "synced ${#FILES[@]} files from pi-code/ -> field-node/  (config.json left as-is)"
