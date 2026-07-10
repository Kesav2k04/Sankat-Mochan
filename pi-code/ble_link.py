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
from typing import Callable, Dict, List, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

import chainlog as clog
import node as nodemod

ATT_HEADER = 3
MIN_MTU = 23             # the BLE spec floor, and bleak's BlueZ placeholder value

# A subscribe or write that never gets an ATT response hangs until the spec's 30 s
# ATT transaction timeout, which then drops the link. Fail sooner and say why.
GATT_OP_TIMEOUT_S = 10.0


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

    def __init__(self, address: str, char_uuid: str, logger, chain: clog.ChainLog, node_name: str):
        self.address = address
        self.name = f"ble:{address}"
        self._char = char_uuid
        self._log = logger
        self._chain = chain
        self._node = node_name
        self._client: Optional[BleakClient] = None
        self._max_write = 0
        self._subscribed = False

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

    def detach(self) -> None:
        self._client = None
        self._max_write = 0
        self._subscribed = False

    async def send(self, raw: bytes, msg_id: str) -> bool:
        if not self.ready:
            # Not a debug detail: the message is now lost, and nobody is holding it.
            self._log.warning("[%s] LOST %s — the phone is not connected right now, "
                              "so there is nowhere to deliver it", self._node, msg_id)
            self._chain.emit(clog.DROP, self._node, radio=self.name, msg_id=msg_id,
                             size=len(raw), reason="not_connected")
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


class BleManager:
    """Keeps one BLE central connection alive per Pi-side node, with reconnect."""

    def __init__(self, cfg: Dict, logger, chain: clog.ChainLog):
        self._cfg = cfg["ble"]
        self._log = logger
        self._chain = chain
        self._tasks: List[asyncio.Task] = []

    async def discover(self) -> List[BLEDevice]:
        """Devices whose *live* advertisement carries the mesh service UUID.

        BlueZ hands back everything it currently knows about a device, merging scan
        responses and cached properties, so `BleakScanner`'s own service filter is not
        enough: a phone can surface here on an address that is not the one the mesh
        app is advertising on. Re-check the UUID against the advertisement we were
        actually given this scan, and drop anything that does not carry it — picking
        such an address connects fine, then wedges on the first GATT operation.
        """
        svc = self._cfg["service_uuid"].lower()
        timeout = float(self._cfg["scan_timeout_s"])
        self._log.info("looking for phones running the mesh app (%.0f second scan)...", timeout)
        found = await BleakScanner.discover(timeout=timeout, service_uuids=[svc], return_adv=True)

        devices: List[BLEDevice] = []
        for device, adv in found.values():
            advertised = {u.lower() for u in (adv.service_uuids or ())}
            label = f"{device.address} ({device.name or 'name not shared'}, {adv.rssi} dBm)"
            if svc in advertised:
                self._log.info("  found a phone running the mesh app: %s", label)
                devices.append(device)
            else:
                self._log.info("  ignoring %s — it is not advertising the mesh app", label)
        return devices

    async def resolve_peers(self) -> Dict[str, str]:
        """Map node name -> phone BLE address, from config or by discovery."""
        configured = {k: v for k, v in self._cfg["peers"].items() if v}
        if len(configured) == 2:
            self._log.info("using configured peers: %s", configured)
            return configured

        devices = await self.discover()
        addrs = sorted({d.address for d in devices})
        if len(addrs) < 2:
            found = ", ".join(addrs) if addrs else "none"
            raise RuntimeError(
                f"I need 2 phones running the mesh app, but I can see {len(addrs)} ({found}). "
                "Open the app on both phones, pick a role, and keep the screen on."
            )
        if len(addrs) > 2:
            raise RuntimeError(
                f"I can see {len(addrs)} phones running the mesh app ({', '.join(addrs)}) and "
                "cannot tell which two you mean. Close the app on the others, or name the two "
                "you want under \"ble\": {\"peers\": {\"field\": \"...\", \"gateway\": \"...\"}} "
                "in config.json."
            )
        # Deterministic so a rerun keeps the same phone on the same side of the link.
        auto = {"field": addrs[0], "gateway": addrs[1]}
        auto.update(configured)
        self._log.info("phone %s is the FIELD phone (the person sending for help)", auto["field"])
        self._log.info("phone %s is the GATEWAY phone (the rescuer receiving)", auto["gateway"])
        return auto

    def maintain(self, link: BleLink, on_bytes: Callable[[bytes], "asyncio.Future"]) -> asyncio.Task:
        task = asyncio.create_task(self._keep_connected(link, on_bytes), name=f"ble-{link.address}")
        self._tasks.append(task)
        return task

    async def _keep_connected(self, link: BleLink, on_bytes) -> None:
        backoff = list(self._cfg["reconnect_backoff_s"]) or [5]
        attempt = 0
        while True:
            try:
                async with BleakClient(link.address, timeout=20.0) as client:
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
                        asyncio.create_task(on_bytes(bytes(data)))

                    await asyncio.wait_for(client.start_notify(link._char, handler),
                                           timeout=GATT_OP_TIMEOUT_S)
                    link.mark_subscribed()
                    self._log.info("[%s] now listening for messages from this phone", link._node)

                    while client.is_connected:
                        await asyncio.sleep(0.5)
            except asyncio.CancelledError:
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
