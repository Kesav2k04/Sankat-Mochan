"""
CONTRACT 2 — the Pi joins the phone mesh as a BLE central.

The Android app makes every phone a peripheral advertising SERVICE_UUID with one
characteristic that is both WRITE and NOTIFY. We connect, subscribe to notifications
(envelopes flowing phone -> Pi) and write to the same characteristic (Pi -> phone).
From the app's point of view we are just another peer; `BleMeshService.onBytes`
already deduplicates and forwards whatever we hand it. No app change is required.

MTU, and why it matters
-----------------------
`GattServerController.onCharacteristicWriteRequest` treats each write as one complete
envelope — it ignores `offset` and `preparedWrite`. So a 244-byte write MUST fit in a
single ATT packet, which needs an MTU of at least 247. If BlueZ negotiates less, a
long write is split across ATT_PREPARE_WRITE requests and the phone will parse each
fragment as a separate (malformed) envelope. Likewise the phone's notifications are
truncated to MTU-3 bytes. We check the negotiated MTU on connect and refuse to send
oversized frames rather than corrupt them silently.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from bleak import BleakClient, BleakScanner

import chainlog as clog
import node as nodemod

ATT_HEADER = 3
MIN_MTU = 23             # the BLE spec floor, and bleak's BlueZ placeholder value

# A subscribe or write that never gets an ATT response hangs until the spec's 30 s
# ATT transaction timeout, which then drops the link. Fail sooner and say why.
GATT_OP_TIMEOUT_S = 10.0

# How long a single connect attempt may run. The connect handshake holds the adapter
# lock (BlueZ won't scan and connect at once), so a long timeout on a phone that has
# rotated away starves discovery for everyone. A live phone answers in a second or
# two; this ceiling only bites on a phone that is genuinely gone.
CONNECT_TIMEOUT_S = 10.0

# The app's scan-response beacon: one role byte, then the node id in ASCII.
# Must stay in step with MeshRole's ordinals in BleMeshService.kt.
ROLE_NAMES = {0: "victim", 1: "responder", 2: "relay"}
MAX_NODE_ID = 8

# Frames that could not be delivered because the phone's BLE link was down are held and
# replayed on reconnect (Android drops the link routinely — MAC rotation, duty cycling).
# Bounded so a long outage can't hoard memory; stale frames are skipped at replay time
# (the phone's own NACK loop covers anything older). 128 comfortably holds a whole
# voice clip (<= 45 chunks) plus interleaved status traffic.
REPLAY_MAX_FRAMES = 128
REPLAY_MAX_AGE_S = 90.0


async def negotiated_mtu(client: BleakClient, logger, name: str) -> int:
    """The real ATT MTU, asking BlueZ for it when bleak hasn't looked it up yet.

    bleak's BlueZ backend hardcodes `mtu_size` to 23 — the spec minimum — until
    `_acquire_mtu()` has run; its own docstring says so, and it emits a UserWarning.
    Believing that placeholder caps us at 20-byte writes, which refuses every real
    SOS envelope. Workaround adapted from bleak's own `examples/mtu_size.py` (MIT).
    """
    backend = getattr(client, "_backend", client)
    if getattr(backend, "_mtu_size", None) is not None:
        return int(backend._mtu_size)

    acquire = getattr(backend, "_acquire_mtu", None)
    if acquire is None:                      # non-BlueZ backend: mtu_size is honest
        return int(client.mtu_size)
    try:
        await acquire()
    except Exception as e:
        logger.warning("[%s] could not ask Bluetooth for the real message-size limit (%s) — "
                       "assuming the %d-byte minimum", name, type(e).__name__, MIN_MTU)
        return MIN_MTU
    return int(getattr(backend, "_mtu_size", MIN_MTU) or MIN_MTU)


class BleLink(nodemod.Link):
    kind = "ble"

    def __init__(self, address: str, char_uuid: str, logger, chain: clog.ChainLog,
                 node_name: str, device: object = None):
        self.address = address
        self.name = f"ble:{address}"
        self._char = char_uuid
        self._log = logger
        self._chain = chain
        self._node = node_name
        # Latest BLEDevice from a scan. Preferred connect target — see MeshPhone.device.
        # Kept across detach so a reconnect can still use it until the next scan refreshes it.
        self._device = device
        self._client: Optional[BleakClient] = None
        self._max_write = 0
        self._subscribed = False
        # Store-and-forward for BLE outages: (raw, msg_id, t_mono) awaiting reconnect.
        self._replay: "deque[tuple[bytes, str, float]]" = deque(maxlen=REPLAY_MAX_FRAMES)

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def ready(self) -> bool:
        """Connected *and* subscribed. A link that connected but never completed its
        subscribe is wedged: writing to it stalls until the ATT timeout kills it."""
        return self.connected and self._subscribed

    def attach(self, client: BleakClient, mtu: int) -> None:
        self._client = client
        self._max_write = max(0, mtu - ATT_HEADER)
        if self._max_write < 244:
            self._log.warning(
                "[%s] PROBLEM: this phone's Bluetooth will only accept %d bytes per message, "
                "but a full SOS is up to 244. Anything bigger will be refused rather than "
                "chopped in half (the phone would read the pieces as garbage).",
                self._node, self._max_write)
            self._log.warning(
                "[%s]   fix: have the app call requestMtu(247) when the Pi connects.",
                self._node)
        else:
            self._log.info("[%s] phone connected — Bluetooth will carry up to %d bytes "
                           "per message, enough for a full SOS", self._node, self._max_write)

    def mark_subscribed(self) -> None:
        self._subscribed = True

    async def flush_replay(self) -> None:
        """Deliver every frame that queued up while the phone was offline. Called right
        after a (re)connect completes its subscribe. Stale frames are skipped — anything
        older than REPLAY_MAX_AGE_S is better recovered by the phone's own NACK loop than
        replayed out of context. The phone's dedup drops any frame it already has."""
        if not self._replay:
            return
        batch, now = [], time.monotonic()
        while self._replay:
            raw, msg_id, t = self._replay.popleft()
            if now - t <= REPLAY_MAX_AGE_S:
                batch.append((raw, msg_id))
        if not batch:
            return
        self._log.info("[%s] phone is back — replaying %d held frame(s)",
                       self._node, len(batch))
        sent = 0
        for i, (raw, msg_id) in enumerate(batch):
            if not self.ready:            # link dropped again mid-replay: re-hold the rest
                self._replay.extend((r, m, now) for r, m in batch[i:])
                break
            if await self.send(raw, msg_id):
                sent += 1
        if sent:
            self._log.info("[%s] replay done — %d frame(s) delivered", self._node, sent)

    def retarget(self, address: str, device: object = None) -> None:
        """Follow the phone to a new Bluetooth address after Android rotated its MAC.

        Without this, the reconnect loop keeps dialling the phone's OLD address forever
        (BleakDeviceNotFoundError / InProgress) while the phone is really advertising on a
        fresh one — every delivery to it is then LOST. `_keep_connected` reads `self.address`
        (and `self._device`) afresh each cycle, so updating them here makes the next
        reconnect land on the live address. No-op when the address has not changed."""
        # Always refresh the BLEDevice from the latest scan, even when the address is
        # unchanged — a fresh handle is what makes the next connect land reliably.
        if device is not None:
            self._device = device
        if not address or address == self.address:
            return
        self._log.info("[%s] phone moved to a new Bluetooth address (%s -> %s); Android "
                       "rotates it — reconnecting there", self._node, self.address, address)
        self.address = address
        self.name = f"ble:{address}"

    def detach(self) -> None:
        self._client = None
        self._max_write = 0
        self._subscribed = False

    async def send(self, raw: bytes, msg_id: str, *,
                   repeats: int | None = None, post_delay_s: float = 0.0) -> bool:
        # BLE writes are ACKed at the ATT layer and point-to-point, so the LoRa airtime
        # knobs (repeats / inter-chunk yield) do not apply — accept and ignore them so
        # MeshNode can call every link uniformly.
        del repeats, post_delay_s
        if not self.ready:
            # The phone is between BLE connections (Android drops/rotates routinely).
            # Hold the frame and replay it the moment the link is back — this is what
            # keeps a voice clip complete on the receiving phone instead of arriving
            # with holes it then has to NACK for one round-trip at a time.
            self._replay.append((raw, msg_id, time.monotonic()))
            self._log.info("[%s] phone offline — holding %s to replay on reconnect "
                           "(%d frame(s) waiting)", self._node, msg_id, len(self._replay))
            self._chain.emit(clog.DROP, self._node, radio=self.name, msg_id=msg_id,
                             size=len(raw), reason="queued_for_reconnect")
            return False
        if self._max_write and len(raw) > self._max_write:
            self._log.error("[%s] LOST %s — it is %d bytes, but this phone's Bluetooth only "
                            "accepts %d bytes per message. Not delivered.",
                            self._node, msg_id, len(raw), self._max_write)
            self._chain.emit(clog.DROP, self._node, radio=self.name, msg_id=msg_id,
                             size=len(raw), reason="mtu_too_small")
            return False
        try:
            assert self._client is not None
            await asyncio.wait_for(
                self._client.write_gatt_char(self._char, raw, response=True),
                timeout=GATT_OP_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            self._log.warning("[%s] could not hand %s to the phone: it did not answer the "
                              "write within %.0fs", self._node, msg_id, GATT_OP_TIMEOUT_S)
            return False
        except Exception as e:
            # The exception *message* carries the ATT error code; the class name alone
            # ("BleakGATTProtocolError") says nothing about why the phone refused.
            self._log.warning("[%s] could not hand %s to the phone: %s: %s",
                              self._node, msg_id, type(e).__name__, e)
            return False

        import envelope as env
        self._chain.emit(clog.BLE_TX, self._node, radio=self.name, msg_id=msg_id,
                         sha=env.digest(raw), size=len(raw))
        self._log.info("[%s] Pi --Bluetooth--> phone: DELIVERED %s (%d bytes)",
                       self._node, msg_id, len(raw))
        return True


@dataclass(frozen=True)
class MeshPhone:
    """One phone running the app, as seen in a single scan."""
    address: str
    node_id: str
    role: str
    rssi: int
    # The scan's BLEDevice handle. Connecting to THIS (not the bare address string) is
    # the reliable path on BlueZ: a bare MAC forces bleak to re-discover the device and
    # then fails with BleakDeviceNotFoundError the moment Android has rotated its address.
    # Excluded from eq/hash/repr so MeshPhone stays comparable and printable as before.
    device: object = field(default=None, compare=False, repr=False)

    def describe(self) -> str:
        return f"{self.node_id} ({self.role}, {self.rssi} dBm, {self.address})"


def parse_beacon(payload: bytes) -> Optional[tuple]:
    """Decode the app's service-data beacon: [role byte][node id ascii].

    Untrusted input (CLAUDE.md #8): every field is length- and range-checked, and a
    beacon that fails any check is discarded rather than half-trusted.
    """
    if not payload or len(payload) < 2 or len(payload) > 1 + MAX_NODE_ID:
        return None
    role = ROLE_NAMES.get(payload[0])
    if role is None:
        return None
    try:
        node_id = payload[1:].decode("ascii")
    except UnicodeDecodeError:
        return None
    if not node_id.isalnum():
        return None
    return role, node_id


class BleManager:
    """Keeps the BLE central connections alive, with reconnect. A Pi-side node may
    hold any number of phones."""

    def __init__(self, cfg: Dict, logger, chain: clog.ChainLog):
        self._cfg = cfg["ble"]
        self._log = logger
        self._chain = chain
        self._tasks: List[asyncio.Task] = []
        # BlueZ serialises scanning and connecting on the one adapter. Letting N
        # reconnect loops and the discovery scan all hit it at once just trades
        # org.bluez.Error.InProgress failures around until nothing gets through —
        # scans starve, rotated phones are never re-found, and the mesh livelocks.
        # Every adapter-owning operation (scan, connect handshake) takes this lock;
        # an established connection does not hold it.
        self._adapter_lock = asyncio.Lock()

    async def discover(self) -> tuple:
        """Scan once. Returns (phones, stale_addresses).

        `phones` are advertisers carrying a readable role beacon; `stale_addresses` are
        advertisers running a build old enough that it broadcasts no beacon at all.
        They are counted separately because they mean two different things to the
        operator: one is "pick a role", the other is "reinstall the app".

        Two reasons not to trust the address here. BlueZ merges scan responses and
        cached properties, so a device can surface on an address the mesh app is not
        actually serving on — connecting to it succeeds, then wedges on the first GATT
        operation. And Android rotates its resolvable private address, so the same
        phone appears under a different MAC between runs. The node id in the beacon is
        the only stable identity we have.
        """
        svc = self._cfg["service_uuid"].lower()
        timeout = float(self._cfg["scan_timeout_s"])
        self._log.info("looking for phones running the mesh app (%.0f second scan)...", timeout)
        async with self._adapter_lock:
            found = await BleakScanner.discover(timeout=timeout, service_uuids=[svc],
                                                return_adv=True)

        phones: List[MeshPhone] = []
        stale: List[str] = []
        for device, adv in found.values():
            advertised = {u.lower() for u in (adv.service_uuids or ())}
            if svc not in advertised:
                self._log.info("  ignoring %s — it is not advertising the mesh app", device.address)
                continue
            beacon = {k.lower(): v for k, v in (adv.service_data or {}).items()}.get(svc)
            parsed = parse_beacon(bytes(beacon)) if beacon else None
            if parsed is None:
                stale.append(device.address)
                continue
            role, node_id = parsed
            phone = MeshPhone(device.address, node_id, role, adv.rssi, device=device)
            self._log.info("  found phone %s", phone.describe())
            phones.append(phone)
        return phones, stale

    async def resolve_roster(self) -> Dict[str, List[MeshPhone]]:
        """Split the phones across the two radios: responders sit behind the gateway
        radio, everyone else behind the field radio.

        That split is the whole point. A victim and a responder on the same radio would
        talk to each other over Bluetooth through this Pi and never key the transmitter;
        putting them on opposite radios means an SOS can only arrive by crossing 433 MHz.
        """
        phones, stale = await self.discover()

        # A phone that broadcasts no role is running a build from before the beacon
        # existed. Say that, rather than blaming the operator's role choice.
        if not phones and stale:
            raise RuntimeError(
                f"{len(stale)} phone(s) are running the mesh app, but none of them broadcast "
                "a role, so I cannot tell a rescuer from someone calling for help. They are on "
                "an old build: rebuild the app and reinstall it on every phone."
            )
        if stale:
            self._log.warning(
                "%d phone(s) are on an old build and will be left out of the mesh (%s). "
                "Rebuild and reinstall to include them.", len(stale), ", ".join(stale))
        if not phones:
            raise RuntimeError(
                "No phone is running the mesh app. Open it on each phone, pick a role, "
                "and keep the screen on."
            )

        # Android rotates its BLE address, so the same phone can appear twice in one
        # scan. Collapse on node id and keep whichever address was heard loudest.
        by_node: Dict[str, MeshPhone] = {}
        for p in phones:
            best = by_node.get(p.node_id)
            if best is None or p.rssi > best.rssi:
                by_node[p.node_id] = p
        if len(by_node) < len(phones):
            self._log.info("  (%d addresses collapsed to %d phones by node id — "
                           "Android rotates its Bluetooth address)", len(phones), len(by_node))

        responders = [p for p in by_node.values() if p.role == "responder"]
        others = sorted((p for p in by_node.values() if p.role != "responder"),
                        key=lambda p: p.node_id)

        # Do not gate the mesh on both roles being present. In particular, a victim's
        # SOS must reach the command post while there are zero responders — that is the
        # moment at which dispatch is needed most. gateway.py keeps scanning after
        # startup and attaches responders whenever they appear.
        responders.sort(key=lambda p: p.rssi, reverse=True)
        roster = {"field": others, "gateway": responders}
        for name, group in roster.items():
            if group:
                self._log.info("radio '%s' will carry %d phone(s): %s", name, len(group),
                               ", ".join(p.describe() for p in group))
        return roster

    def maintain(self, link: BleLink, on_bytes: Callable[[bytes], None],
                 on_state: Callable[[bool], None] | None = None) -> asyncio.Task:
        task = asyncio.create_task(
            self._keep_connected(link, on_bytes, on_state), name=f"ble-{link.address}"
        )
        self._tasks.append(task)
        return task

    async def _keep_connected(self, link: BleLink, on_bytes, on_state=None) -> None:
        backoff = list(self._cfg["reconnect_backoff_s"]) or [5]
        attempt = 0
        while True:
            announced = False
            client: Optional[BleakClient] = None
            try:
                # Connect by the scan's BLEDevice when we have one — a bare MAC string
                # makes bleak re-discover the device first, which fails with
                # BleakDeviceNotFoundError the moment Android rotates the address.
                target = link._device or link.address
                # Only the handshake holds the adapter lock; a connected session
                # doesn't block scans or the other links' reconnects.
                async with self._adapter_lock:
                    client = BleakClient(target, timeout=CONNECT_TIMEOUT_S)
                    await client.connect()
                attempt = 0
                if client.services.get_characteristic(link._char) is None:
                    raise RuntimeError(
                        f"{link.address} accepted the connection but does not serve the "
                        "mesh characteristic — this is not the phone's mesh-app address. "
                        "Pin the right one under \"ble\".\"peers\" in config.json."
                    )
                mtu = await negotiated_mtu(client, self._log, link._node)
                link.attach(client, mtu)
                self._chain.emit(clog.PEER, link._node, radio=link.name,
                                 state="connected", mtu=mtu)

                def handler(_char, data: bytearray) -> None:
                    # Hand off to the node's bounded intake queue (a fast, non-blocking
                    # enqueue) rather than spawning a task per notification — an
                    # unbounded task-per-frame was a DoS vector (mesh-transmission.md D1).
                    on_bytes(bytes(data))

                await asyncio.wait_for(client.start_notify(link._char, handler),
                                       timeout=GATT_OP_TIMEOUT_S)
                link.mark_subscribed()
                if on_state is not None:
                    on_state(True)
                    announced = True
                self._log.info("[%s] now listening for messages from this phone", link._node)
                # Deliver whatever queued while the phone was away (voice chunks
                # especially — this is what keeps a clip complete on the phone).
                await link.flush_replay()

                while client.is_connected:
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                if client is not None:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                raise
            except asyncio.TimeoutError:
                self._log.warning(
                    "[%s] %s connected but never answered the subscribe within %.0fs — "
                    "dropping it rather than waiting for the link to time out",
                    link._node, link.address, GATT_OP_TIMEOUT_S)
            except Exception as e:
                self._log.warning("[%s] Bluetooth trouble with %s: %s: %s",
                                  link._node, link.address, type(e).__name__, e)
            finally:
                if announced and on_state is not None:
                    on_state(False)
                if client is not None:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                if link.connected:
                    link.detach()

            link.detach()
            self._chain.emit(clog.PEER, link._node, radio=link.name, state="disconnected")
            delay = backoff[min(attempt, len(backoff) - 1)]
            attempt += 1
            self._log.info("[%s] trying to reconnect to the phone in %ss", link._node, delay)
            await asyncio.sleep(delay)

    async def close(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
