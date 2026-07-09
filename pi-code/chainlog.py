"""
Two logs, two audiences.

`gateway.log`  — human-readable narrative at whatever level you set (DEBUG..ERROR).
`chain.jsonl`  — one JSON object per hop event, machine-readable, append-only.

The chain log is the *evidence* that a message crossed the air rather than being
shuffled between two objects inside one Python process. For every envelope id you
get a LORA_TX row on one radio and a LORA_RX row on the other carrying:

  * `sha`        — sha256 of the exact payload bytes, taken on both sides
  * `rssi_dbm`   — read out of the receiving chip's RegPktRssiValue
  * `snr_db`     — read out of RegPktSnrValue
  * `airtime_ms` — measured wall time between entering TX and TxDone firing

rssi/snr are produced by the SX1278's own demodulator. There is no code path that
invents them, and no way to obtain them without a real frame arriving over RF.
Kill the receiving radio's power and the LORA_RX row simply stops appearing.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Hop events
BLE_RX = "BLE_RX"        # envelope arrived from a phone
BLE_TX = "BLE_TX"        # envelope written out to a phone
LORA_TX = "LORA_TX"      # frame handed to the radio, TxDone confirmed
LORA_RX = "LORA_RX"      # frame demodulated off the air
DROP = "DROP"            # rejected: malformed / duplicate / bad CRC / oversized
PEER = "PEER"            # BLE peer connected or disconnected
UPLINK = "UPLINK"        # posted to the AI-PC dashboard
START = "START"          # process/radio lifecycle


class ChainLog:
    """Append-only JSONL hop log. Safe to call from any thread."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._t0 = time.monotonic()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8")

    def emit(self, event: str, node: str, **fields: Any) -> None:
        row: Dict[str, Any] = {
            "t_wall": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "t_rel_ms": round((time.monotonic() - self._t0) * 1000, 1),
            "event": event,
            "node": node,
        }
        # Drop unset optionals so rows stay narrow and greppable.
        row.update({k: v for k, v in fields.items() if v is not None})
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())  # a crash mid-demo must not lose the evidence

    def close(self) -> None:
        with self._lock:
            self._fh.close()

    @property
    def path(self) -> Path:
        return self._path


def setup(cfg: Dict[str, Any]) -> tuple[logging.Logger, ChainLog]:
    log_cfg = cfg["log"]
    base = Path(log_cfg["dir"])
    if not base.is_absolute():
        base = Path(__file__).resolve().parent / base
    base.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, str(log_cfg["level"]).upper(), logging.INFO)
    logger = logging.getLogger("sankat")
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)-5s %(name)s: %(message)s", "%H:%M:%S")

    fh = logging.FileHandler(base / log_cfg["text_file"], encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if log_cfg.get("console", True):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    return logger, ChainLog(base / log_cfg["chain_file"])


def summarise(chain_path: Path) -> str:
    """Read back the chain log and state, per envelope id, whether it crossed LoRa.

    A message counts as LoRa-delivered only when the SAME payload hash appears in a
    LORA_TX row on one radio and a LORA_RX row on a DIFFERENT radio. Matching only
    on id would be satisfied by a purely in-process hand-off; matching on the hash
    across two distinct radios cannot be.
    """
    tx: Dict[str, list] = {}
    rx: Dict[str, list] = {}
    seen_ids: list[str] = []

    with chain_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            mid, sha = row.get("msg_id"), row.get("sha")
            if not mid or not sha:
                continue
            if mid not in seen_ids:
                seen_ids.append(mid)
            if row["event"] == LORA_TX:
                tx.setdefault(mid, []).append(row)
            elif row["event"] == LORA_RX:
                rx.setdefault(mid, []).append(row)

    if not seen_ids:
        return "No envelopes recorded yet."

    lines = [f"{'envelope':<16} {'via LoRa':<9} {'radio TX -> RX':<24} {'RSSI':>7} {'SNR':>7}"]
    lines.append("-" * 70)
    for mid in seen_ids:
        proved = False
        detail = ""
        for t in tx.get(mid, []):
            for r in rx.get(mid, []):
                if t["sha"] == r["sha"] and t.get("radio") != r.get("radio"):
                    proved = True
                    detail = f"{t.get('radio')} -> {r.get('radio')}"
                    rssi = f"{r.get('rssi_dbm')} dBm"
                    snr = f"{r.get('snr_db')} dB"
                    break
            if proved:
                break
        if proved:
            lines.append(f"{mid:<16} {'YES':<9} {detail:<24} {rssi:>7} {snr:>7}")
        else:
            why = "no LORA_RX" if mid in tx else "never transmitted"
            lines.append(f"{mid:<16} {'NO':<9} {why:<24} {'-':>7} {'-':>7}")
    return "\n".join(lines)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "logs" / "chain.jsonl"
    if not target.exists():
        sys.exit(f"no chain log at {target}")
    print(summarise(target))
