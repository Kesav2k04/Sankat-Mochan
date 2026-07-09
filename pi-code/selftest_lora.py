#!/usr/bin/env python3
"""
Hardware self-test for the LoRa tier. No phones, no BLE — just the two radios.

Scenarios exercised:
  1. A real SOS envelope crosses radio A -> radio B over 433 MHz.
  2. The reverse direction (an ACCEPTED ack) crosses B -> A.
  3. Payload integrity: sha256 of the bytes at TX equals sha256 at RX.
  4. CONTRACT 1 dedup: a re-sent id is accepted once and forwarded once.
  5. Untrusted input: a malformed frame is dropped, not parsed.
  6. NEGATIVE CONTROL: with radio B asleep, nothing is delivered. This is the test
     that distinguishes a real radio link from two objects talking in one process.

Exit code 0 = every scenario passed.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import chainlog as clog
import config as cfgmod
import envelope as env
import node as nodemod
from sx127x import MODE_SLEEP, MODE_STDBY, Radio, gpio_cleanup, gpio_init


class CapturingLink(nodemod.Link):
    """Stands in for the phone on the far side: records what the node would deliver."""
    kind = "sink"

    def __init__(self, name: str):
        self.name = name
        self.received: List[bytes] = []

    async def send(self, raw: bytes, msg_id: str) -> bool:
        self.received.append(raw)
        return True


def sos(seq: int, gist: str) -> env.Envelope:
    return env.Envelope(
        id=f"selftest-{seq}", type="SOS", origin="selftest",
        urgency=4, category="trapped", location_hint="block C",
        gist=gist, lang="ta", lat=12.9716, lng=77.5946,
        ts=int(time.time() * 1000), hops=0,
    )


async def wait_for(predicate, timeout: float = 8.0, poll: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(poll)
    return False


async def main() -> int:
    cfg = cfgmod.load()
    logger, chain = clog.setup(cfg)
    lora_cfg = cfgmod.lora_config(cfg)
    csma = cfg["lora"]["csma"]

    gpio_init()
    radios = {}
    for name in ("field", "gateway"):
        r = cfg["radios"][name]
        radios[name] = Radio(name, r["cs"], r["rst_gpio"], r["dio0_gpio"], lora_cfg)

    results: List[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        results.append((label, ok, detail))
        # Detail is diagnostic: only useful when the assertion failed.
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail and not ok else ""))

    try:
        for r in radios.values():
            r.open()
            logger.info("radio %s ready on CE%d (rst=%d dio0=%d)", r.name, r.cs, r.rst_gpio, r.dio0_gpio)
            chain.emit(clog.START, r.name, radio=r.name, freq_hz=lora_cfg.frequency_hz,
                       sf=lora_cfg.spreading_factor, bw_hz=lora_cfg.bandwidth_hz,
                       tx_power_dbm=lora_cfg.tx_power_dbm)

        loop = asyncio.get_running_loop()

        field = nodemod.MeshNode("field", logger, chain)
        gateway = nodemod.MeshNode("gateway", logger, chain)

        lora_a = nodemod.LoRaLink(radios["field"], lora_cfg, csma, logger, chain, "field")
        lora_b = nodemod.LoRaLink(radios["gateway"], lora_cfg, csma, logger, chain, "gateway")
        sink_a = CapturingLink("phoneA-sim")
        sink_b = CapturingLink("phoneB-sim")

        field.add_link(lora_a)
        field.add_link(sink_a)
        gateway.add_link(lora_b)
        gateway.add_link(sink_b)

        # Radio RX fires on its own thread; hop back onto the event loop to do mesh work.
        def bridge(n: nodemod.MeshNode, link: nodemod.LoRaLink):
            def cb(pkt):
                asyncio.run_coroutine_threadsafe(n.on_lora_frame(link, pkt), loop)
            return cb

        radios["field"].start_receiving(bridge(field, lora_a))
        radios["gateway"].start_receiving(bridge(gateway, lora_b))
        await asyncio.sleep(0.2)

        print("\n=== LoRa tier self-test ===")
        print(f"  {lora_cfg.frequency_hz/1e6:.3f} MHz  SF{lora_cfg.spreading_factor}  "
              f"BW{lora_cfg.bandwidth_hz//1000}k  CR4/{lora_cfg.coding_rate}  "
              f"{lora_cfg.tx_power_dbm} dBm  sync=0x{lora_cfg.sync_word:02X}\n")

        # --- 1 + 3: forward path, byte-exact -------------------------------
        m1 = sos(1, "Two people trapped on the second floor, water rising")
        raw1 = m1.encode()
        await field.originate(m1)
        got = await wait_for(lambda: len(sink_b.received) >= 1)
        check("SOS crosses radio A -> radio B", got, "no delivery within 8 s" if not got else "")

        if got:
            delivered = env.decode(sink_b.received[0])
            check("envelope survives the air intact",
                  delivered is not None and delivered.id == m1.id and delivered.gist == m1.gist,
                  f"gist={delivered.gist!r}" if delivered else "undecodable")
            print(f"         gist round-tripped: {delivered.gist!r}" if delivered else "")
            check("hop counter incremented across the LoRa tier",
                  delivered is not None and delivered.hops == 1,
                  f"hops={delivered.hops if delivered else '?'}")
            # The bytes the gateway re-encodes differ (hops+1), so compare on the wire
            # payload the radio actually carried, recorded in the chain log.
            check("payload hash identical at TX and RX",
                  _sha_matches(chain.path, m1.id), "see chain.jsonl")

        # --- 2: reverse path ------------------------------------------------
        ack = env.Envelope(id="selftest-ack-1", type="ACCEPTED", origin="control",
                           ref_id=m1.id, gist="Help is on the way", lang="ta",
                           ts=int(time.time() * 1000))
        await gateway.originate(ack)
        got_back = await wait_for(lambda: len(sink_a.received) >= 1)
        check("ACCEPTED crosses radio B -> radio A", got_back,
              "no delivery within 8 s" if not got_back else "")

        # --- 4: dedup at the receiver ---------------------------------------
        # originate() deliberately re-transmits (this is how the phone's flushOutbox
        # re-sends to a peer that appeared late). The guarantee under test is that the
        # RECEIVING node recognises the id and refuses to deliver it a second time.
        before = len(sink_b.received)
        await field.originate(m1)
        await asyncio.sleep(1.5)
        check("re-sent id is received again but delivered only once",
              len(sink_b.received) == before, f"sink grew to {len(sink_b.received)}")

        # --- 5: untrusted input ---------------------------------------------
        before = len(sink_b.received)
        radios["field"].send(b'{"i":"bad","t":"SOS"' + b"x" * 40)   # truncated JSON
        await asyncio.sleep(1.5)
        check("malformed frame dropped, not parsed", len(sink_b.received) == before,
              f"sink grew to {len(sink_b.received)}")

        # --- 6: NEGATIVE CONTROL --------------------------------------------
        # Put radio B to sleep. If anything still reaches phoneB-sim, the "LoRa" path
        # is a lie and the two nodes are talking through memory.
        radios["gateway"].stop_receiving()
        radios["gateway"]._set_mode(MODE_SLEEP)
        before = len(sink_b.received)
        m2 = sos(2, "This must never arrive — radio B is asleep")
        await field.originate(m2)
        await asyncio.sleep(2.5)
        silent = len(sink_b.received) == before
        check("NEGATIVE CONTROL: radio B asleep -> nothing delivered", silent,
              "something arrived without a working receiver!" if not silent else "")

        radios["gateway"]._set_mode(MODE_STDBY)
        radios["gateway"].start_receiving(bridge(gateway, lora_b))

        print("\n=== chain log: did each envelope really cross the air? ===")
        print(clog.summarise(chain.path))
        print(f"\nchain log: {chain.path}")

    finally:
        for r in radios.values():
            try:
                r.close()
            except Exception:
                pass
        gpio_cleanup()
        chain.close()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} scenarios passed")
    return 0 if passed == len(results) else 1


def _sha_matches(chain_path: Path, msg_id: str) -> bool:
    import json
    tx = rx = None
    for line in chain_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("msg_id") != msg_id:
            continue
        if row["event"] == clog.LORA_TX:
            tx = row["sha"]
        elif row["event"] == clog.LORA_RX:
            rx = row["sha"]
    return tx is not None and tx == rx


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
