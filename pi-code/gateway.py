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

Prerequisites: SPI enabled, `sudo rfkill unblock bluetooth`, the mesh app open on two
phones (airplane mode is fine — re-enable Bluetooth only).
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
from sx127x import LoraConfig, Radio, gpio_cleanup, gpio_init
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
                healthy = await loop.run_in_executor(None, radio.in_lora_mode)
            except Exception as e:
                logger.error("radio '%s' stopped answering: %s: %s", name, type(e).__name__, e)
                continue
            if healthy:
                continue
            logger.error("radio '%s' fell out of LoRa mode — it reset itself. "
                         "Re-initialising; nothing it 'sent' meanwhile left the antenna.", name)
            chain.emit(clog.START, name, radio=name, result="fell_out_of_lora")
            try:
                await loop.run_in_executor(None, radio.reinit)
            except Exception as e:
                logger.error("radio '%s' could not be revived: %s: %s", name, type(e).__name__, e)
                chain.emit(clog.DROP, name, radio=name, reason="radio_dead")
                continue
            logger.warning("radio '%s' is back in LoRa mode", name)
            chain.emit(clog.START, name, radio=name, result="reinit")


async def resolve_peers_waiting(manager, cfg, logger, stop: asyncio.Event):
    """Poll until at least one responder and one other phone appear (or the operator gives up)."""
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
            if isinstance(msg, (env.VoiceChunk, env.VoiceNack)):
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
            for name in NODE_NAMES:
                for phone in peers[name]:
                    bl = ble_link.BleLink(phone.address, cfg["ble"]["char_uuid"],
                                          logger, chain, name)
                    nodes[name].add_link(bl)
                    n = nodes[name]
                    manager.maintain(bl, lambda raw, n=n, bl=bl: n.on_ble_bytes(bl, raw))
            logger.info("READY. An SOS from any phone on the field radio now travels: "
                        "phone -> Bluetooth -> Pi -> 433 MHz -> Pi -> Bluetooth -> responder. "
                        "The responder is on the far radio, so nothing reaches it without "
                        "crossing the air.")
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
