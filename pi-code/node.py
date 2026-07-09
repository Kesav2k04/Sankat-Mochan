"""
CONTRACT 1 mesh semantics, Pi-side.

A MeshNode owns a set of links and one dedup set. On an inbound frame it:
  validate -> dedup by envelope id -> act -> re-send to every link EXCEPT the source.

That last clause is the whole loop-freedom argument, and it is why the gateway runs
**two** MeshNodes rather than one:

    field   = MeshNode(links=[lora_A, ble_phone_A])
    gateway = MeshNode(links=[lora_B, ble_phone_B])

The two nodes share no dedup set and no link. Nothing inside this process connects
phone A's BLE link to phone B's BLE link. The ONLY edge between the two halves is the
433 MHz hop from radio A to radio B. If the RF link dies, phone B receives nothing —
by construction, not by convention.

(A single node holding both radios would be worse than useless: radio A would mark the
id seen on transmit, and radio B would then drop its own reception as a duplicate.)
"""
from __future__ import annotations

import asyncio
import random
import threading
import time
from typing import Awaitable, Callable, Dict, List, Optional

import chainlog as clog
import envelope as env
from sx127x import LoraConfig, LoraError, Radio, RxPacket

# One radio at a time may key up: both antennas are inches apart on the same channel,
# so a simultaneous transmit is a guaranteed collision, not a race we can tolerate.
_AIRWAVES = threading.Lock()


def signal_words(rssi_dbm: float, snr_db: float) -> str:
    """`strong signal (-67 dBm, SNR 10.5 dB)` — the number, plus what it means."""
    if rssi_dbm >= -70:
        quality = "strong signal"
    elif rssi_dbm >= -90:
        quality = "usable signal"
    elif rssi_dbm >= -110:
        quality = "weak signal"
    else:
        quality = "barely-there signal"
    return f"{quality} ({rssi_dbm:.0f} dBm, SNR {snr_db:.1f} dB)"


class Link:
    """Something a node can push envelope bytes at."""
    kind: str = "?"
    name: str = "?"

    async def send(self, raw: bytes, msg_id: str) -> bool:
        raise NotImplementedError


class LoRaLink(Link):
    kind = "lora"

    def __init__(self, radio: Radio, lora_cfg: LoraConfig, csma: Dict, logger, chain: clog.ChainLog, node_name: str):
        self.radio = radio
        self.name = radio.name
        self._cfg = lora_cfg
        self._csma = csma
        self._log = logger
        self._chain = chain
        self._node = node_name
        self._repeats = 1

    def set_repeats(self, n: int) -> None:
        self._repeats = max(1, n)

    def _wait_for_quiet(self) -> bool:
        """Carrier sense. Returns False if the channel never went quiet in time."""
        if not self._csma.get("enabled", True):
            return True
        threshold = self._csma["rssi_threshold_dbm"]
        deadline = time.monotonic() + self._csma["max_wait_ms"] / 1000.0
        while time.monotonic() < deadline:
            if self.radio.channel_rssi_dbm() < threshold:
                return True
            time.sleep(random.uniform(0.005, self._csma["max_backoff_ms"] / 1000.0))
        return False

    def _send_blocking(self, raw: bytes, msg_id: str) -> bool:
        sha = env.digest(raw)
        ok_any = False
        for attempt in range(self._repeats):
            with _AIRWAVES:
                if not self._wait_for_quiet():
                    self._log.warning("[%s] the 433 MHz channel is busy — sending %s anyway",
                                      self._node, msg_id)
                try:
                    airtime = self.radio.send(raw)
                except LoraError as e:
                    self._log.error("[%s] radio FAILED to transmit %s: %s", self._node, msg_id, e)
                    self._chain.emit(clog.DROP, self._node, radio=self.name, msg_id=msg_id,
                                     sha=sha, reason="tx_failed")
                    continue
            ok_any = True
            self._chain.emit(
                clog.LORA_TX, self._node, radio=self.name, msg_id=msg_id, sha=sha,
                size=len(raw), airtime_ms=round(airtime * 1000, 1),
                airtime_theory_ms=round(self._cfg.airtime_s(len(raw)) * 1000, 1),
                attempt=attempt + 1, tx_power_dbm=self._cfg.tx_power_dbm,
                freq_hz=self._cfg.frequency_hz, sf=self._cfg.spreading_factor,
                bw_hz=self._cfg.bandwidth_hz,
            )
            retry = f", retry {attempt + 1}" if attempt else ""
            self._log.info("[%s] Pi --433 MHz--> air: sent %s (%d bytes, %.0f ms on air%s)",
                           self._node, msg_id, len(raw), airtime * 1000, retry)
        return ok_any

    async def send(self, raw: bytes, msg_id: str) -> bool:
        # A 244-byte frame at SF7 is ~400 ms on air; never block the event loop with it.
        return await asyncio.get_running_loop().run_in_executor(None, self._send_blocking, raw, msg_id)


class MeshNode:
    def __init__(self, name: str, logger, chain: clog.ChainLog,
                 on_accept: Optional[Callable[[env.Envelope], Awaitable[None]]] = None):
        self.name = name
        self.links: List[Link] = []
        self._seen: set[str] = set()
        self._seen_lock = threading.Lock()
        self._log = logger
        self._chain = chain
        self._on_accept = on_accept

    def add_link(self, link: Link) -> None:
        self.links.append(link)

    def _mark_seen(self, msg_id: str) -> bool:
        """True the first time an id is seen — mirrors MessageStore.markSeen."""
        with self._seen_lock:
            if msg_id in self._seen:
                return False
            self._seen.add(msg_id)
            return True

    _DROP_WORDS = {
        "crc_error": "it arrived corrupted (radio checksum failed)",
        "malformed": "it was not a valid mesh message",
    }

    def _drop(self, source: str, raw: bytes, reason: str, **extra) -> None:
        self._chain.emit(clog.DROP, self.name, radio=source, size=len(raw),
                         sha=env.digest(raw), reason=reason, **extra)
        self._log.info("[%s] ignored %d bytes from %s: %s", self.name, len(raw), source,
                       self._DROP_WORDS.get(reason, reason))

    def _log_text(self, msg: env.Envelope) -> None:
        """Print what the person actually wrote, on its own line, indented."""
        body = env.message_text(msg)
        if body:
            self._log.info("           message: %s", body)

    async def on_lora_frame(self, link: LoRaLink, pkt: RxPacket) -> None:
        if not pkt.crc_ok:
            self._drop(link.name, pkt.payload, "crc_error", rssi_dbm=pkt.rssi_dbm, snr_db=pkt.snr_db)
            return

        sha = env.digest(pkt.payload)
        msg = env.decode(pkt.payload)
        if msg is None:
            self._drop(link.name, pkt.payload, "malformed", rssi_dbm=pkt.rssi_dbm, snr_db=pkt.snr_db)
            return

        # rssi/snr come straight off the demodulator — this row is the proof of flight.
        self._chain.emit(
            clog.LORA_RX, self.name, radio=link.name, msg_id=msg.id, sha=sha,
            size=len(pkt.payload), rssi_dbm=pkt.rssi_dbm, snr_db=pkt.snr_db,
            hops=msg.hops, type=msg.type, origin=msg.origin,
        )
        self._log.info("[%s] air --433 MHz--> Pi: got %s, %s, %d hop(s) so far",
                       self.name, env.describe(msg), signal_words(pkt.rssi_dbm, pkt.snr_db),
                       msg.hops)
        self._log_text(msg)

        await self._accept(msg, source=link)

    async def on_ble_bytes(self, link: Link, raw: bytes) -> None:
        msg = env.decode(raw)
        if msg is None:
            self._drop(link.name, raw, "malformed")
            return
        self._chain.emit(clog.BLE_RX, self.name, radio=link.name, msg_id=msg.id,
                         sha=env.digest(raw), size=len(raw), hops=msg.hops,
                         type=msg.type, origin=msg.origin)
        self._log.info("[%s] phone --Bluetooth--> Pi: got %s, %d hop(s) so far",
                       self.name, env.describe(msg), msg.hops)
        self._log_text(msg)
        await self._accept(msg, source=link)

    async def _accept(self, msg: env.Envelope, source: Optional[Link]) -> None:
        if not self._mark_seen(msg.id):
            self._chain.emit(clog.DROP, self.name, radio=getattr(source, "name", "local"),
                             msg_id=msg.id, reason="duplicate")
            self._log.info("[%s] already handled %s before — not passing it on again "
                           "(this is normal; it stops messages looping forever)",
                           self.name, msg.id)
            return

        if self._on_accept is not None:
            try:
                await self._on_accept(msg)
            except Exception as e:  # an uplink failure must not stop the mesh
                self._log.warning("[%s] could not send %s to the dashboard: %s",
                                  self.name, msg.id, type(e).__name__)

        await self._forward(msg.bumped(), source)

    async def _forward(self, msg: env.Envelope, source: Optional[Link]) -> None:
        targets = [l for l in self.links if l is not source]
        if not targets:
            self._log.info("[%s] nowhere left to pass %s — this node is the end of the line",
                           self.name, msg.id)
            return
        raw = msg.encode()
        await asyncio.gather(*(self._send_one(l, raw, msg) for l in targets))

    async def _send_one(self, link: Link, raw: bytes, msg: env.Envelope) -> None:
        try:
            ok = await link.send(raw, msg.id)
        except Exception as e:
            self._log.warning("[%s] could not pass %s to %s: %s",
                              self.name, msg.id, link.name, type(e).__name__)
            ok = False
        if not ok:
            self._chain.emit(clog.DROP, self.name, radio=link.name, msg_id=msg.id,
                             sha=env.digest(raw), reason="send_failed")

    async def originate(self, msg: env.Envelope) -> None:
        """Inject a locally-created envelope (used by the self-test and by tools)."""
        self._mark_seen(msg.id)
        await self._forward(msg, source=None)
