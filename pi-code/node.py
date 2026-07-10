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
from collections import OrderedDict
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

    async def send(self, raw: bytes, msg_id: str, *,
                   repeats: Optional[int] = None, post_delay_s: float = 0.0) -> bool:
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

    def _recover(self) -> bool:
        """Re-initialise a radio that reset itself. Returns False if it stays broken."""
        try:
            self.radio.reinit()
        except Exception as e:
            self._log.error("[%s] radio '%s' could not be revived: %s: %s",
                            self._node, self.name, type(e).__name__, e)
            self._chain.emit(clog.DROP, self._node, radio=self.name, reason="radio_dead")
            return False
        self._log.warning("[%s] radio '%s' had reset itself; re-initialised it",
                          self._node, self.name)
        self._chain.emit(clog.START, self._node, radio=self.name, result="reinit")
        return True

    def _send_blocking(self, raw: bytes, msg_id: str, repeats: int) -> bool:
        sha = env.digest(raw)
        ok_any = False
        for attempt in range(repeats):
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
                    # A radio that has fallen out of LoRa mode will fail every frame from
                    # here on. Put it back before the next one, or a 45-chunk voice clip
                    # dies 45 times over.
                    if not self._recover():
                        return ok_any
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

    async def send(self, raw: bytes, msg_id: str, *,
                   repeats: Optional[int] = None, post_delay_s: float = 0.0) -> bool:
        # A 244-byte frame at SF7 is ~400 ms on air; never block the event loop with it.
        # `repeats` overrides the link-global default per frame (voice sends once — its NACK
        # loop repairs loss — while an SOS keeps its retries). `post_delay_s` yields the air
        # briefly after a voice chunk so a queued SOS can win _AIRWAVES mid-clip rather than
        # waiting out all ~45 chunks (mesh-transmission.md A6/D3).
        n = self._repeats if repeats is None else max(1, repeats)
        ok = await asyncio.get_running_loop().run_in_executor(
            None, self._send_blocking, raw, msg_id, n)
        if post_delay_s > 0:
            await asyncio.sleep(post_delay_s)
        return ok


# Sentinel item kinds on a MeshNode's intake queue.
_RX_LORA = "lora"
_RX_BLE = "ble"


class _RxItem:
    """One decoded inbound frame waiting on an intake lane. Carrying the decoded envelope
    (decode happens once, at classification) lets the drainer route by urgency without
    re-parsing, and lets on_lora keep the packet's rssi/snr for the proof-of-flight log."""
    __slots__ = ("kind", "link", "msg", "raw", "pkt")

    def __init__(self, kind, link, msg, raw, pkt=None):
        self.kind = kind      # _RX_LORA | _RX_BLE
        self.link = link
        self.msg = msg        # decoded env.Envelope / VoiceChunk / VoiceNack
        self.raw = raw        # original bytes (for digest/size in logs)
        self.pkt = pkt        # RxPacket for LoRa (rssi/snr), else None


class MeshNode:
    def __init__(self, name: str, logger, chain: clog.ChainLog,
                 on_accept: Optional[Callable[[env.Envelope], Awaitable[None]]] = None,
                 *, seen_max: int = 4096, queue_max: int = 256,
                 global_frames_per_s: float = 50.0, voice_post_delay_s: float = 0.02):
        self.name = name
        self.links: List[Link] = []
        # Yield after each voice chunk on LoRa so an SOS can grab the air mid-clip (A6).
        self.voice_post_delay_s = max(0.0, float(voice_post_delay_s))
        # Dedup ring: an OrderedDict used as an LRU. Bounded so a flood of forged ids over
        # untrusted RF (CLAUDE.md #8) can't grow it without limit. The mesh TTL (MAX_HOPS)
        # bounds how long a genuine duplicate can loop, so a recent window is all we need.
        self._seen: "OrderedDict[str, None]" = OrderedDict()
        self._seen_max = max(1, seen_max)
        self._seen_lock = threading.Lock()
        self._log = logger
        self._chain = chain
        self._on_accept = on_accept

        # Bounded, TWO-LANE RX intake (mesh-transmission.md D1 + MJ1/MJ2). One drainer per
        # node (per-node, not global, preserves the two-MeshNode loop-freedom isolation this
        # file's module docstring depends on) services two bounded queues:
        #   - CRITICAL: SOS envelopes (any urgency). Drained FIRST and EXEMPT from the global
        #     rate cap — an SOS is admitted, always ("never lose an SOS"). Overflow here is a
        #     LOUD alarm, never a silent drop; under real load it must never fill.
        #   - NORMAL: everything else (voice chunks, NACK, DELIVERED/ACCEPTED, dispatch
        #     echoes, malformed). Rate-limited + bounded; overflow is drop-and-log.
        # Frames are DECODED at classification (the untrusted-input validation point anyway,
        # cheap + bounded) so the drainer can route by type/urgency without re-parsing.
        self._queue_max = max(1, queue_max)
        self._crit_q: "Optional[asyncio.Queue]" = None
        self._norm_q: "Optional[asyncio.Queue]" = None
        self._loop: "Optional[asyncio.AbstractEventLoop]" = None
        self._drainer: Optional[asyncio.Task] = None
        # Spoof-proof global cap on the NORMAL lane: a ceiling on frames/sec ACROSS ALL
        # origins. Origins are unauthenticated, so a per-origin bucket is bypassable (forge a
        # fresh origin per frame); a global token bucket cannot be evaded — it trusts no id
        # (M4). The critical lane is deliberately NOT subject to it.
        self._rate = float(global_frames_per_s)
        self._tokens = float(global_frames_per_s)
        self._tokens_ts = time.monotonic()
        self._dropped_overrun = 0
        self._dropped_rate = 0
        self.critical_alarm = False           # surfaced like outbox_alarm if CRITICAL fills
        self._critical_overflow = 0
        self.rx_progress = time.monotonic()   # liveness heartbeat (A7)

    def add_link(self, link: Link) -> None:
        self.links.append(link)

    # ---- bounded two-lane RX intake (D1 + MJ1/MJ2) ----
    def start_intake(self, loop: "asyncio.AbstractEventLoop",
                     stop: asyncio.Event) -> asyncio.Task:
        """Create the two bounded lanes + single drainer task. Call once, on the loop."""
        self._loop = loop
        self._crit_q = asyncio.Queue(maxsize=self._queue_max)
        self._norm_q = asyncio.Queue(maxsize=self._queue_max)
        self._drainer = loop.create_task(self._drain(stop), name=f"rx-drain-{self.name}")
        return self._drainer

    @staticmethod
    def _is_critical(msg) -> bool:
        """An SOS envelope of ANY urgency is critical: it must never be delayed behind, or
        dropped in favour of, voice/NACK/status traffic. Voice chunks carry a ClassVar
        type='VOICE'; a text SOS is env.Envelope with type='SOS'."""
        return isinstance(msg, env.Envelope) and getattr(msg, "type", None) == "SOS"

    def submit_lora(self, link: "LoRaLink", pkt: RxPacket) -> None:
        """Enqueue a LoRa frame from the radio RX thread (thread-safe onto the loop)."""
        loop = self._loop
        if loop is None or self._crit_q is None:
            return
        loop.call_soon_threadsafe(self._classify_and_offer, _RX_LORA, link, pkt)

    def submit_ble(self, link: Link, raw: bytes) -> None:
        """Enqueue a BLE frame. Called from the notification handler (already on the loop)."""
        if self._crit_q is None:
            return
        self._classify_and_offer(_RX_BLE, link, raw)

    def _classify_and_offer(self, kind, link, payload) -> None:
        """Runs on the event loop. Validates + decodes the untrusted frame once, drops the
        undecodable/corrupt here, and routes the rest to the critical or normal lane."""
        if kind == _RX_LORA:
            pkt = payload
            if not pkt.crc_ok:
                self._drop(getattr(link, "name", "?"), pkt.payload, "crc_error",
                           rssi_dbm=pkt.rssi_dbm, snr_db=pkt.snr_db)
                return
            raw = pkt.payload
            msg = env.decode(raw)
            if msg is None:
                self._drop(getattr(link, "name", "?"), raw, "malformed",
                           rssi_dbm=pkt.rssi_dbm, snr_db=pkt.snr_db)
                return
            item = _RxItem(kind, link, msg, raw, pkt)
        else:
            raw = payload
            msg = env.decode(raw)
            if msg is None:
                self._drop(getattr(link, "name", "?"), raw, "malformed")
                return
            item = _RxItem(kind, link, msg, raw, None)

        if self._is_critical(msg):
            self._offer_critical(item)
        else:
            self._offer_normal(item)

    def _offer_critical(self, item: "_RxItem") -> None:
        """Enqueue an SOS on the critical lane. It must never be silently dropped: overflow
        is a loud alarm the operator sees, not a discard. Under real load this cannot fill
        (SOS volume is tiny); if it does, something is very wrong and must be visible."""
        assert self._crit_q is not None
        try:
            self._crit_q.put_nowait(item)
        except asyncio.QueueFull:
            self._critical_overflow += 1
            self.critical_alarm = True
            # Not rule-10-suppressed: losing an SOS is the one thing we promised never to do.
            self._log.error(
                "[%s] CRITICAL INTAKE FULL — an SOS (%s from %s) could not be queued "
                "(%d overflow). The gateway is overwhelmed; operator action needed. The "
                "message is NOT confirmed delivered.",
                self.name, getattr(item.msg, "id", "?"),
                getattr(item.msg, "origin", "?"), self._critical_overflow)

    def _offer_normal(self, item: "_RxItem") -> None:
        """Non-blocking enqueue on the normal lane; drop-and-log on overflow rather than
        block a producer."""
        assert self._norm_q is not None
        try:
            self._norm_q.put_nowait(item)
        except asyncio.QueueFull:
            self._dropped_overrun += 1
            if self._dropped_overrun & 0x3F == 1:   # log sparsely — no log-flood
                self._log.warning("[%s] normal RX lane full — dropping frames (%d dropped "
                                  "so far). Shedding non-SOS load under a burst.",
                                  self.name, self._dropped_overrun)

    def _allow(self) -> bool:
        """Global token bucket for the NORMAL lane only. Refills at self._rate tokens/sec,
        capped at one second's burst. The critical lane never consults this."""
        now = time.monotonic()
        self._tokens = min(self._rate, self._tokens + (now - self._tokens_ts) * self._rate)
        self._tokens_ts = now
        if self._tokens < 1.0:
            return False
        self._tokens -= 1.0
        return True

    async def _handle(self, item: "_RxItem") -> None:
        try:
            if item.kind == _RX_LORA:
                await self._handle_lora(item)
            else:
                await self._handle_ble(item)
        except Exception as e:   # one bad frame must never kill the drainer
            self._log.warning("[%s] error handling an RX frame: %s: %s",
                              self.name, type(e).__name__, e)

    async def _drain(self, stop: asyncio.Event) -> None:
        """Single consumer. Empties the CRITICAL lane fully first (rate-exempt), then serves
        ONE normal item (rate-limited), then loops — so an SOS can never queue behind a
        burst of ~45 voice chunks (MJ2) and can never be dropped by the rate cap (MJ1)."""
        assert self._crit_q is not None and self._norm_q is not None
        crit, norm = self._crit_q, self._norm_q
        while not stop.is_set():
            # 1) Drain everything critical, unconditionally.
            while True:
                try:
                    item = crit.get_nowait()
                except asyncio.QueueEmpty:
                    break
                self.rx_progress = time.monotonic()
                await self._handle(item)

            # 2) One normal item, subject to the global rate cap. Wait briefly so we wake
            #    promptly when either lane gets work, without a busy-loop.
            try:
                item = await asyncio.wait_for(norm.get(), timeout=0.05)
            except asyncio.TimeoutError:
                self.rx_progress = time.monotonic()   # idle is still alive
                continue
            self.rx_progress = time.monotonic()
            if not self._allow():
                self._dropped_rate += 1
                if self._dropped_rate & 0x3F == 1:
                    self._log.warning("[%s] over the %.0f frames/s ingest ceiling — "
                                      "dropping non-SOS (%d dropped). Flood protection.",
                                      self.name, self._rate, self._dropped_rate)
                self._drop(getattr(item.link, "name", "?"), item.raw, "rate_limited")
                continue
            await self._handle(item)

    def _mark_seen(self, msg_id: str) -> bool:
        """True the first time an id is seen — mirrors MessageStore.markSeen. Bounded LRU:
        the oldest id is evicted once the ring is full."""
        with self._seen_lock:
            if msg_id in self._seen:
                self._seen.move_to_end(msg_id)
                return False
            self._seen[msg_id] = None
            if len(self._seen) > self._seen_max:
                self._seen.popitem(last=False)
            return True

    _DROP_WORDS = {
        "crc_error": "it arrived corrupted (radio checksum failed)",
        "malformed": "it was not a valid mesh message",
        "rate_limited": "the ingest rate ceiling was exceeded (flood protection)",
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
        """Public entry decoding a raw LoRa packet (used by selftest_lora.py, which drives
        a node without the intake queue). The live gateway path decodes at classification
        and calls _handle_lora with the result instead."""
        if not pkt.crc_ok:
            self._drop(link.name, pkt.payload, "crc_error", rssi_dbm=pkt.rssi_dbm, snr_db=pkt.snr_db)
            return
        msg = env.decode(pkt.payload)
        if msg is None:
            self._drop(link.name, pkt.payload, "malformed", rssi_dbm=pkt.rssi_dbm, snr_db=pkt.snr_db)
            return
        await self._handle_lora(_RxItem(_RX_LORA, link, msg, pkt.payload, pkt))

    async def on_ble_bytes(self, link: Link, raw: bytes) -> None:
        """Public entry decoding raw BLE bytes. See on_lora_frame — the live path decodes at
        classification and calls _handle_ble with the result."""
        msg = env.decode(raw)
        if msg is None:
            self._drop(link.name, raw, "malformed")
            return
        await self._handle_ble(_RxItem(_RX_BLE, link, msg, raw, None))

    async def _handle_lora(self, item: "_RxItem") -> None:
        link, msg, pkt = item.link, item.msg, item.pkt
        # rssi/snr come straight off the demodulator — this row is the proof of flight.
        self._chain.emit(
            clog.LORA_RX, self.name, radio=link.name, msg_id=msg.id, sha=env.digest(item.raw),
            size=len(item.raw), rssi_dbm=pkt.rssi_dbm, snr_db=pkt.snr_db,
            hops=msg.hops, type=msg.type, origin=msg.origin,
        )
        self._log.info("[%s] air --433 MHz--> Pi: got %s, %s, %d hop(s) so far",
                       self.name, env.describe(msg), signal_words(pkt.rssi_dbm, pkt.snr_db),
                       msg.hops)
        self._log_text(msg)
        await self._accept(msg, source=link)

    async def _handle_ble(self, item: "_RxItem") -> None:
        link, msg = item.link, item.msg
        self._chain.emit(clog.BLE_RX, self.name, radio=link.name, msg_id=msg.id,
                         sha=env.digest(item.raw), size=len(item.raw), hops=msg.hops,
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

    def _tx_policy(self, msg) -> tuple[Optional[int], float]:
        """Per-frame LoRa airtime policy (A6). Voice chunks send ONCE (their NACK repair
        loop recovers any dropped piece, so blind repeats are wasted airtime) and yield the
        air briefly afterwards so a queued SOS can win _AIRWAVES mid-clip instead of waiting
        out ~45 chunks. Everything else (SOS, dispatch, NACK) keeps the link default."""
        if getattr(msg, "type", None) == "VOICE":
            return 1, self.voice_post_delay_s
        return None, 0.0

    async def _send_one(self, link: Link, raw: bytes, msg: env.Envelope) -> None:
        repeats, post_delay_s = self._tx_policy(msg)
        try:
            ok = await link.send(raw, msg.id, repeats=repeats, post_delay_s=post_delay_s)
        except Exception as e:
            self._log.warning("[%s] could not pass %s to %s: %s: %s",
                              self.name, msg.id, link.name, type(e).__name__, e)
            ok = False
        if not ok:
            self._chain.emit(clog.DROP, self.name, radio=link.name, msg_id=msg.id,
                             sha=env.digest(raw), reason="send_failed")

    async def originate(self, msg: env.Envelope) -> None:
        """Inject a locally-created envelope (used by the self-test and by tools)."""
        self._mark_seen(msg.id)
        await self._forward(msg, source=None)
