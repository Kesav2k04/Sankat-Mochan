#!/usr/bin/env python3
"""
Sankat-Mochan LoRa gateway: phone <-BLE-> Pi <-433 MHz-> Pi <-BLE-> phone.

    phone A ──BLE──► [field node]  ══ 433 MHz ══►  [gateway node] ──BLE──► phone B
    phone A ◄──BLE── [field node]  ◄══ 433 MHz ══  [gateway node] ◄──BLE── phone B

The two Pi-side nodes share no state and no link (see node.py). The only edge between
them is the radio hop, so a message from phone A physically cannot reach phone B
without crossing 433 MHz. Pull the antenna off radio B and delivery stops.

Run:
    ../.venv/bin/python gateway.py                 # auto-discover both phones
    SANKAT_LOG__LEVEL=DEBUG ../.venv/bin/python gateway.py
    ../.venv/bin/python chainlog.py                # did each envelope cross the air?

Prerequisites: SPI enabled, `sudo rfkill unblock bluetooth`, and the mesh app open on
at least one phone (airplane mode is fine — re-enable Bluetooth only). Responders may
join later without restarting the gateway.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ble_link
import chainlog as clog
import config as cfgmod
import envelope as env
import node as nodemod
from sx127x import LONG_RANGE_MODE, LoraConfig, Radio, gpio_cleanup, gpio_init
from uplink import EdgeUplink

NODE_NAMES = ("field", "gateway")

PROBE_MAGIC = b"SANKAT-PROBE:"


def _derive_ws_url(http_url: str) -> str:
    """http://host:port/sos  →  ws://host:port/gateway (the EDGE-LINK channel)."""
    from urllib.parse import urlparse, urlunparse
    p = urlparse(http_url)
    scheme = "wss" if p.scheme == "https" else "ws"
    return urlunparse((scheme, p.netloc, "/gateway", "", "", ""))


async def startup_probe(radios: Dict[str, Radio], lora_cfg: LoraConfig,
                        logger, chain: clog.ChainLog) -> bool:
    """Send one frame A -> B and require it to arrive, before any phone is attached.

    This is the difference between "the gateway started" and "the gateway can actually
    carry a message". It runs on the raw radios, before the MeshNodes are wired up, so
    the probe can never leak onto a phone. The payload is deliberately NOT a valid
    envelope — nothing downstream would accept it even if it escaped.
    """
    if not lora_cfg:
        return True

    nonce = os.urandom(8).hex().encode()
    payload = PROBE_MAGIC + nonce
    got = threading.Event()
    seen: Dict[str, object] = {}

    def collect(pkt) -> None:
        if pkt.payload == payload:
            seen["pkt"] = pkt
            got.set()

    radios["gateway"].start_receiving(collect)
    await asyncio.sleep(0.1)
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, radios["field"].send, payload)
        arrived = await loop.run_in_executor(None, got.wait, 5.0)
    finally:
        radios["gateway"].stop_receiving()

    if not arrived:
        logger.error("RADIO CHECK FAILED: radio 'field' transmitted, radio 'gateway' heard nothing.")
        logger.error("  Check both antennas are screwed on, and that both radios use the same "
                     "frequency, spreading factor, bandwidth, coding rate and sync word.")
        chain.emit(clog.START, "probe", result="failed")
        return False

    pkt = seen["pkt"]
    logger.info("radio check PASSED: 'field' spoke, 'gateway' heard it — %s. "
                "The 433 MHz link works.", nodemod.signal_words(pkt.rssi_dbm, pkt.snr_db))
    chain.emit(clog.START, "probe", result="ok", radio="field->gateway",
               rssi_dbm=pkt.rssi_dbm, snr_db=pkt.snr_db)
    return True


async def radio_watchdog(radios: Dict[str, Radio], logger, chain: clog.ChainLog,
                         stop: asyncio.Event, period_s: float = 5.0) -> None:
    """Keep both radios in LoRa mode for as long as the gateway is up.

    An SX1278 that resets — brownout, a glitch on the RST line — comes back in FSK. It
    still answers SPI, RegVersion still reads 0x12, and pre-flight would still pass. But
    RegIrqFlags then addresses a different register whose bits read as set, so a transmit
    'completes' in 0.1 ms having radiated nothing. `Radio.send()` now refuses in that
    state; this brings the radio back rather than waiting for the next message to fail.
    """
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=period_s)
            return                                  # stop was set
        except asyncio.TimeoutError:
            pass
        for name, radio in radios.items():
            try:
                op = await loop.run_in_executor(None, radio.op_mode)
                if op & LONG_RANGE_MODE:
                    continue
                # Re-initialising means pulsing RST on a radio that may be perfectly fine.
                # One glitched SPI read is not enough to justify that, so ask again.
                await asyncio.sleep(0.05)
                op2 = await loop.run_in_executor(None, radio.op_mode)
                if op2 & LONG_RANGE_MODE:
                    logger.warning("radio '%s': RegOpMode read 0x%02X then 0x%02X — ignoring the "
                                   "first as a glitch, the radio is still in LoRa mode", name, op, op2)
                    continue
            except Exception as e:
                logger.error("radio '%s' stopped answering: %s: %s", name, type(e).__name__, e)
                continue

            logger.error("radio '%s' is out of LoRa mode (RegOpMode=0x%02X, twice) — it reset "
                         "itself. Re-initialising; nothing it 'sent' meanwhile left the antenna.",
                         name, op2)
            chain.emit(clog.START, name, radio=name, result="fell_out_of_lora", op_mode=op2)
            try:
                await loop.run_in_executor(None, radio.reinit)
                op3 = await loop.run_in_executor(None, radio.op_mode)
            except Exception as e:
                logger.error("radio '%s' could not be revived: %s: %s", name, type(e).__name__, e)
                chain.emit(clog.DROP, name, radio=name, reason="radio_dead")
                continue
            # Say what actually happened, not what we hoped for. The old message claimed
            # success without ever looking, which made a repeating fault unreadable.
            if op3 & LONG_RANGE_MODE:
                logger.warning("radio '%s' is back in LoRa mode (RegOpMode=0x%02X)", name, op3)
                chain.emit(clog.START, name, radio=name, result="reinit", op_mode=op3)
            else:
                logger.error("radio '%s' STILL not in LoRa mode after re-init (RegOpMode=0x%02X). "
                             "Check the RST wire on GPIO%d and the module's 3.3 V supply.",
                             name, op3, radio.rst_gpio)
                chain.emit(clog.DROP, name, radio=name, reason="reinit_failed", op_mode=op3)


async def resolve_peers_waiting(manager, cfg, logger, stop: asyncio.Event):
    """Poll until any valid mesh phone appears (or the operator gives up)."""
    retry = float(cfg["ble"]["peer_retry_s"])
    while not stop.is_set():
        try:
            return await manager.resolve_roster()
        except RuntimeError as e:
            if not cfg["ble"]["wait_for_peers"]:
                raise
            # Rule 10: an operator-facing failure is a message, not a traceback.
            logger.warning("%s", e)
            logger.info("still waiting — I will look again in %.0fs "
                        "(press Ctrl-C to stop)", retry)
            try:
                await asyncio.wait_for(stop.wait(), timeout=retry)
            except asyncio.TimeoutError:
                pass
    return None


def attach_phone(phone, manager, nodes, cfg, logger, chain: clog.ChainLog,
                 edge: EdgeUplink | None = None) -> None:
    """Attach one discovered phone to the correct side of the physical radio hop."""
    name = "gateway" if phone.role == "responder" else "field"
    bl = ble_link.BleLink(phone.address, cfg["ble"]["char_uuid"], logger, chain, name)
    nodes[name].add_link(bl)
    node = nodes[name]
    on_state = None
    if phone.role == "responder" and edge is not None:
        on_state = lambda connected: edge.set_peer_state(
            phone.node_id, phone.role, connected
        )
    manager.maintain(
        bl, lambda raw, node=node, bl=bl: node.on_ble_bytes(bl, raw), on_state=on_state
    )
    logger.info("attached phone %s to radio '%s'", phone.describe(), name)


async def discover_new_peers(manager, nodes, cfg, logger, chain: clog.ChainLog,
                             stop: asyncio.Event,
                             attached_node_ids: set[str],
                             edge: EdgeUplink | None = None) -> None:
    """Keep accepting phones after startup, notably responders arriving later.

    Node ids are stable while Android BLE addresses rotate, so they are the identity
    key. Existing links own their reconnect loop; this scanner only creates links for
    phones that have not been attached during this gateway run.
    """
    retry = float(cfg["ble"]["peer_retry_s"])
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=retry)
            return
        except asyncio.TimeoutError:
            pass

        try:
            roster = await manager.resolve_roster()
        except RuntimeError as e:
            logger.info("phone scan: %s", e)
            continue
        except Exception as e:
            logger.warning("phone scan failed (%s); trying again in %.0fs",
                           type(e).__name__, retry)
            continue

        for name in NODE_NAMES:
            for phone in roster[name]:
                if phone.node_id in attached_node_ids:
                    continue
                attach_phone(phone, manager, nodes, cfg, logger, chain, edge)
                attached_node_ids.add(phone.node_id)
                if phone.role == "responder":
                    logger.info("responder %s joined — acceptance updates can now travel "
                                "back across 433 MHz", phone.node_id)


async def run() -> int:
    cfg = cfgmod.load()
    logger, chain = clog.setup(cfg)
    lora_cfg = cfgmod.lora_config(cfg)
    csma = cfg["lora"]["csma"]

    logger.info("radio settings: %.3f MHz, spreading factor %d, bandwidth %d kHz, "
                "coding rate 4/%d, power %d dBm, sync word 0x%02X (both radios must match)",
                lora_cfg.frequency_hz / 1e6, lora_cfg.spreading_factor,
                lora_cfg.bandwidth_hz // 1000, lora_cfg.coding_rate,
                lora_cfg.tx_power_dbm, lora_cfg.sync_word)

    gpio_init()
    radios: Dict[str, Radio] = {}
    manager = ble_link.BleManager(cfg, logger, chain)
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    edge: EdgeUplink | None = None
    edge_task: asyncio.Task | None = None
    peer_discovery_task: asyncio.Task | None = None
    try:
        for name in NODE_NAMES:
            r = cfg["radios"][name]
            radio = Radio(name, r["cs"], r["rst_gpio"], r["dio0_gpio"], lora_cfg)
            radio.open()
            radios[name] = radio
            logger.info("radio '%s' is powered up and listening (chip-select CE%d, "
                        "reset pin GPIO%d, data-ready pin GPIO%d)",
                        name, r["cs"], r["rst_gpio"], r["dio0_gpio"])
            chain.emit(clog.START, name, radio=name, freq_hz=lora_cfg.frequency_hz,
                       sf=lora_cfg.spreading_factor, tx_power_dbm=lora_cfg.tx_power_dbm)

        # Prove the RF link before we accept a single byte of real traffic.
        if cfg["lora"]["startup_probe"] and not await startup_probe(radios, lora_cfg, logger, chain):
            return 3

        # Edge link to the AI PC (EDGE-LINK.md): durable, bidirectional, lossless.
        nodes: Dict[str, nodemod.MeshNode] = {}

        async def on_dispatch(env_dict: dict) -> None:
            """Return path: an ACCEPTED / instruction from the AI PC, injected into the
            mesh so it reaches the victim's phone over LoRa/BLE."""
            msg = env.decode(json.dumps(env_dict).encode())
            if msg is None:
                logger.warning("dropping malformed dispatch from the AI PC")
                return
            gw = nodes.get("gateway")
            if gw is not None:
                await gw.originate(msg)
                logger.info("return path: sent %s (%s) back toward the victim",
                            msg.id, msg.type)

        up = cfg["uplink"]
        if up["enabled"]:
            ws_url = up.get("ws") or _derive_ws_url(up["url"])
            edge = EdgeUplink(ws_url, up["url"], up.get("outbox", "edge_outbox.sqlite"),
                              on_dispatch, logger)
            edge_task = asyncio.create_task(edge.run(stop))
            logger.info("edge link to AI PC: %s (durable outbox, HTTP fallback %s)",
                        ws_url, up["url"])

        async def on_accept(msg) -> None:
            # Durable + idempotent: enqueued to the outbox, sent, deleted only on ACK.
            # Voice chunks are opaque binary carried phone-to-phone; the dashboard takes
            # JSON envelopes only, so they are not uplinked (matches the voice-SOS design).
            if isinstance(msg, env.VoiceChunk):
                if edge is not None:
                    edge.send_voice_chunk(msg)
                return
            if isinstance(msg, env.VoiceNack):
                return
            if edge is not None:
                edge.send_envelope(msg.to_dict())

        nodes["field"] = nodemod.MeshNode("field", logger, chain)
        nodes["gateway"] = nodemod.MeshNode("gateway", logger, chain, on_accept=on_accept)

        lora_links = {}
        for name in NODE_NAMES:
            link = nodemod.LoRaLink(radios[name], lora_cfg, csma, logger, chain, name)
            link.set_repeats(cfg["lora"]["tx_repeats"])
            nodes[name].add_link(link)
            lora_links[name] = link

        # Radio RX runs on its own thread; hop back onto the loop to do mesh work.
        for name in NODE_NAMES:
            n, l = nodes[name], lora_links[name]
            radios[name].start_receiving(
                lambda pkt, n=n, l=l: asyncio.run_coroutine_threadsafe(n.on_lora_frame(l, pkt), loop)
            )

        if cfg["ble"]["enabled"]:
            try:
                peers = await resolve_peers_waiting(manager, cfg, logger, stop)
            except RuntimeError as e:
                # Rule 10: an operator-facing failure is a one-line message, not a traceback.
                logger.error("cannot start: %s", e)
                logger.error("hint: `sudo rfkill unblock bluetooth`, then open the app on both "
                             "phones. Or run the radios alone with SANKAT_BLE__ENABLED=false.")
                return 2
            if peers is None:          # operator hit Ctrl-C while we were waiting
                logger.info("stopped before any phone appeared")
                return 0
            attached_node_ids: set[str] = set()
            for name in NODE_NAMES:
                for phone in peers[name]:
                    attach_phone(phone, manager, nodes, cfg, logger, chain, edge)
                    attached_node_ids.add(phone.node_id)
            peer_discovery_task = asyncio.create_task(
                discover_new_peers(manager, nodes, cfg, logger, chain, stop,
                                   attached_node_ids, edge),
                name="ble-peer-discovery",
            )
            logger.info("READY. SOS messages are accepted immediately; no responder phone "
                        "is required. Victim traffic travels phone -> Bluetooth -> Pi -> "
                        "433 MHz -> gateway -> AI PC. I will keep scanning for responders "
                        "and attach them when they appear.")
        else:
            logger.warning("Bluetooth is switched off in the config — running the two radios "
                           "alone, with no phones attached")

        watchdog = asyncio.create_task(radio_watchdog(radios, logger, chain, stop))
        try:
            await stop.wait()
        finally:
            watchdog.cancel()
        logger.info("shutting down")

    finally:
        if peer_discovery_task is not None:
            peer_discovery_task.cancel()
            try:
                await peer_discovery_task
            except asyncio.CancelledError:
                pass
        if edge_task is not None:
            edge_task.cancel()
            try:
                await edge_task
            except asyncio.CancelledError:
                pass
        await manager.close()
        for r in radios.values():
            try:
                r.close()
            except Exception:
                pass
        gpio_cleanup()
        if chain.path.exists():
            print("\n=== did each envelope cross the air? ===")
            print(clog.summarise(chain.path))
        chain.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(run()))
    except KeyboardInterrupt:
        sys.exit(130)
