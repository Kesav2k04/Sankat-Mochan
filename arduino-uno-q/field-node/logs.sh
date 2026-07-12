#!/usr/bin/env bash
#
# Watch the field-node logs.
#
#     ./logs.sh            systemd journal: service start/stop + gateway output (live)
#     ./logs.sh app        the human-readable gateway.log (same as ./run.sh logs)
#     ./logs.sh proof      the chain log — did each envelope really cross the air?
#     ./logs.sh boot       just this boot's journal, from the top (no follow)

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-journal}" in
  app)   exec tail -f "$HERE/logs/gateway.log" ;;
  proof) exec "$HERE/run.sh" proof ;;
  boot)  exec journalctl -u field-node.service -b --no-pager ;;
  *)     exec journalctl -u field-node.service -f -n 100 ;;
esac
