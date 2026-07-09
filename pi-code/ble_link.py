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

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def attach(self, client: BleakClient) -> None:
        self._client = client
        mtu = getattr(client, "mtu_size", 0) or 0
        self._max_write = max(0, mtu - ATT_HEADER)
        if self._max_write < 244:
            self._log.warning(
                "%s: negotiated MTU %d allows only %d-byte frames. Envelopes larger than "
                "that cannot be delivered atomically and will be refused (the phone would "
                "otherwise see fragments as malformed envelopes).",
                self.name, mtu, self._max_write,
            )
        else:
            self._log.info("%s: connected, MTU %d (%d-byte frames OK)", self.name, mtu, self._max_write)

    def detach(self) -> None:
        self._client = None
        self._max_write = 0

    async def send(self, raw: bytes, msg_id: str) -> bool:
        if not self.connected:
            self._log.debug("%s: not connected, cannot deliver %s", self.name, msg_id)
            return False
        if self._max_write and len(raw) > self._max_write:
            self._log.error("%s: refusing to send %s — %dB exceeds the %dB single-write budget",
                            self.name, msg_id, len(raw), self._max_write)
            self._chain.emit(clog.DROP, self._node, radio=self.name, msg_id=msg_id,
                             size=len(raw), reason="mtu_too_small")
            return False
        try:
            assert self._client is not None
            await self._client.write_gatt_char(self._char, raw, response=True)
        except Exception as e:
            self._log.warning("%s: write failed for %s: %s", self.name, msg_id, e)
            return False

        import envelope as env
        self._chain.emit(clog.BLE_TX, self._node, radio=self.name, msg_id=msg_id,
                         sha=env.digest(raw), size=len(raw))
        self._log.info("%s: delivered %s to phone (%dB)", self.name, msg_id, len(raw))
        return True


class BleManager:
    """Keeps one BLE central connection alive per Pi-side node, with reconnect."""

    def __init__(self, cfg: Dict, logger, chain: clog.ChainLog):
        self._cfg = cfg["ble"]
        self._log = logger
        self._chain = chain
        self._tasks: List[asyncio.Task] = []

    async def discover(self) -> List[BLEDevice]:
        svc = self._cfg["service_uuid"].lower()
        timeout = float(self._cfg["scan_timeout_s"])
        self._log.info("scanning %.0fs for phones advertising %s", timeout, svc)
        found = await BleakScanner.discover(timeout=timeout, service_uuids=[svc], return_adv=True)
        devices = [d for d, _adv in found.values()]
        for d in devices:
            self._log.info("  found mesh peer %s (%s)", d.address, d.name or "no name")
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
            raise RuntimeError(
                f"need 2 phones running the mesh app, found {len(addrs)}: {addrs or 'none'}. "
                "Open the app on both phones, pick a role, and keep the screen on."
            )
        # Deterministic so a rerun keeps the same phone on the same side of the link.
        auto = {"field": addrs[0], "gateway": addrs[1]}
        auto.update(configured)
        self._log.info("auto-assigned peers (lowest MAC -> field): %s", auto)
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
                    link.attach(client)
                    self._chain.emit(clog.PEER, link._node, radio=link.name,
                                     state="connected", mtu=getattr(client, "mtu_size", None))

                    def handler(_char, data: bytearray) -> None:
                        asyncio.create_task(on_bytes(bytes(data)))

                    await client.start_notify(link._char, handler)
                    self._log.info("%s: subscribed to mesh notifications", link.name)

                    while client.is_connected:
                        await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._log.warning("%s: %s", link.name, e)
            finally:
                if link.connected:
                    link.detach()

            link.detach()
            self._chain.emit(clog.PEER, link._node, radio=link.name, state="disconnected")
            delay = backoff[min(attempt, len(backoff) - 1)]
            attempt += 1
            self._log.info("%s: reconnecting in %ss", link.name, delay)
            await asyncio.sleep(delay)

    async def close(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
