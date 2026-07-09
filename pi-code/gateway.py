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

NODE_NAMES = ("field", "gateway")

PROBE_MAGIC = b"SANKAT-PROBE:"


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
        logger.error("startup probe FAILED: radio 'field' transmitted, radio 'gateway' heard nothing")
        logger.error("check both antennas are attached, and that both radios share "
                     "frequency/SF/bandwidth/coding-rate/sync-word")
        chain.emit(clog.START, "probe", result="failed")
        return False

    pkt = seen["pkt"]
    logger.info("startup probe OK: field -> gateway, %d dBm, SNR %.1f dB", pkt.rssi_dbm, pkt.snr_db)
    chain.emit(clog.START, "probe", result="ok", radio="field->gateway",
               rssi_dbm=pkt.rssi_dbm, snr_db=pkt.snr_db)
    return True


async def resolve_peers_waiting(manager, cfg, logger, stop: asyncio.Event):
    """Poll for the two phones until they appear (or the operator gives up)."""
    retry = float(cfg["ble"]["peer_retry_s"])
    while not stop.is_set():
        try:
            return await manager.resolve_peers()
        except RuntimeError as e:
            if not cfg["ble"]["wait_for_peers"]:
                raise
            # Rule 10: an operator-facing failure is a message, not a traceback.
            logger.warning("%s", e)
            logger.info("waiting for phones — retrying in %.0fs (Ctrl-C to stop)", retry)
            try:
                await asyncio.wait_for(stop.wait(), timeout=retry)
            except asyncio.TimeoutError:
                pass
    return None


def _make_uplink(cfg: Dict, logger, chain: clog.ChainLog):
    """POST accepted envelopes to the AI-PC dashboard. Optional and best-effort."""
    up = cfg["uplink"]
    if not up["enabled"]:
        return None

    import requests

    url, timeout = up["url"], up["timeout_s"]

    async def hook(msg: env.Envelope) -> None:
        def post():
            return requests.post(url, json=msg.to_dict(), timeout=timeout)
        try:
            resp = await asyncio.get_running_loop().run_in_executor(None, post)
            chain.emit(clog.UPLINK, "gateway", msg_id=msg.id, status=resp.status_code)
            logger.info("uplinked %s -> HTTP %s", msg.id, resp.status_code)
        except Exception as e:
            # Rule 10: never surface a stack trace on the live dashboard path.
            logger.warning("uplink for %s failed: %s", msg.id, type(e).__name__)
            chain.emit(clog.UPLINK, "gateway", msg_id=msg.id, status="failed")

    return hook


async def run() -> int:
    cfg = cfgmod.load()
    logger, chain = clog.setup(cfg)
    lora_cfg = cfgmod.lora_config(cfg)
    csma = cfg["lora"]["csma"]

    logger.info("LoRa: %.3f MHz SF%d BW%dk CR4/%d %d dBm sync=0x%02X",
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

    try:
        for name in NODE_NAMES:
            r = cfg["radios"][name]
            radio = Radio(name, r["cs"], r["rst_gpio"], r["dio0_gpio"], lora_cfg)
            radio.open()
            radios[name] = radio
            logger.info("radio %s up on CE%d (rst=GPIO%d dio0=GPIO%d)",
                        name, r["cs"], r["rst_gpio"], r["dio0_gpio"])
            chain.emit(clog.START, name, radio=name, freq_hz=lora_cfg.frequency_hz,
                       sf=lora_cfg.spreading_factor, tx_power_dbm=lora_cfg.tx_power_dbm)

        # Prove the RF link before we accept a single byte of real traffic.
        if cfg["lora"]["startup_probe"] and not await startup_probe(radios, lora_cfg, logger, chain):
            return 3

        uplink = _make_uplink(cfg, logger, chain)
        nodes = {
            "field": nodemod.MeshNode("field", logger, chain),
            "gateway": nodemod.MeshNode("gateway", logger, chain, on_accept=uplink),
        }

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
                bl = ble_link.BleLink(peers[name], cfg["ble"]["char_uuid"], logger, chain, name)
                nodes[name].add_link(bl)
                n = nodes[name]
                manager.maintain(bl, lambda raw, n=n, bl=bl: n.on_ble_bytes(bl, raw))
            logger.info("gateway live — field<->%s, gateway<->%s", peers["field"], peers["gateway"])
        else:
            logger.warning("ble.enabled is false — LoRa tier only, no phones attached")

        await stop.wait()
        logger.info("shutting down")

    finally:
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
