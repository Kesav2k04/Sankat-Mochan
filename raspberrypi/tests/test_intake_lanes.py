"""
Tests for the two-lane RX intake on MeshNode (mesh-transmission.md MJ1/MJ2).

Drives the drainer directly (the selftest path bypasses it) to prove:
  - an SOS is serviced BEFORE queued non-SOS traffic (SOS-first, MJ2),
  - an SOS is NEVER dropped by the global rate cap that sheds non-SOS under flood (MJ1),
  - the critical lane is exempt from the rate cap,
  - a malformed frame is dropped at intake, not queued.

No hardware: RPi.GPIO / spidev are stubbed so node/sx127x import off-Pi. Pure asyncio.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # raspberrypi/ modules

import asyncio
import logging
import sys
import types


def _stub_hardware() -> None:
    rpi = types.ModuleType("RPi")
    gpio = types.ModuleType("RPi.GPIO")
    for n in ("setmode", "setup", "output", "cleanup", "setwarnings",
              "add_event_detect", "remove_event_detect", "input"):
        setattr(gpio, n, lambda *a, **k: None)
    gpio.BCM = gpio.OUT = gpio.IN = gpio.HIGH = gpio.LOW = gpio.RISING = 0
    rpi.GPIO = gpio
    sys.modules.setdefault("RPi", rpi)
    sys.modules.setdefault("RPi.GPIO", gpio)
    spidev = types.ModuleType("spidev")
    spidev.SpiDev = lambda *a, **k: types.SimpleNamespace(
        open=lambda *a: None, xfer2=lambda *a: [0], close=lambda: None,
        max_speed_hz=0, mode=0)
    sys.modules.setdefault("spidev", spidev)


_stub_hardware()

import envelope as env  # noqa: E402
import node as nodemod  # noqa: E402


class _NullChain:
    def emit(self, *a, **k) -> None:
        pass


class _Link:
    def __init__(self, name="ble:test"):
        self.name = name


def _log():
    lg = logging.getLogger("test-intake")
    lg.addHandler(logging.NullHandler())
    lg.setLevel(logging.CRITICAL)
    return lg


def _make_node(on_accept, **kw) -> nodemod.MeshNode:
    return nodemod.MeshNode("gw", _log(), _NullChain(), on_accept=on_accept, **kw)


def _sos(i: str, urgency: int = 5) -> bytes:
    return env.Envelope(id=i, type="SOS", origin="p1", urgency=urgency).encode()


def _voice_chunk(seq: int, index: int) -> bytes:
    return env.VoiceChunk(origin="p2", seq=seq, index=index, total=50,
                          payload=b"x").encode()


async def _run(coro, timeout=3.0):
    return await asyncio.wait_for(coro, timeout)


# ---------------------------------------------------------------- tests


async def _test_sos_first() -> None:
    """A burst of ~45 voice chunks is queued, then one SOS. The SOS must be handled before
    the bulk of the voice chunks — proving the critical lane jumps the queue (MJ2)."""
    order: list[str] = []

    async def on_accept(msg) -> None:
        order.append(msg.type)

    node = _make_node(on_accept, queue_max=128, global_frames_per_s=10_000)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    node.start_intake(loop, stop)
    link = _Link()

    # Fill the normal lane first, THEN drop in an SOS.
    for i in range(45):
        node.submit_ble(link, _voice_chunk(1, i))
    node.submit_ble(link, _sos("sos-1"))

    # Give the drainer time to process everything.
    for _ in range(200):
        if len(order) >= 46:
            break
        await asyncio.sleep(0.005)
    stop.set()
    await asyncio.sleep(0.02)

    assert "SOS" in order, f"SOS never handled: {order[:5]}"
    sos_pos = order.index("SOS")
    # SOS must be near the front, not after all 45 voice chunks.
    assert sos_pos <= 1, f"SOS was handled at position {sos_pos} (expected first): {order[:5]}"
    print("  ok  test_sos_first (SOS handled at position", sos_pos, ")")


async def _test_sos_never_rate_dropped() -> None:
    """Rate cap is tiny (1/s) and a flood of voice chunks exhausts it, but every SOS must
    still be accepted — the critical lane is rate-exempt (MJ1)."""
    accepted: list[str] = []

    async def on_accept(msg) -> None:
        accepted.append(msg.id)

    node = _make_node(on_accept, queue_max=256, global_frames_per_s=1.0)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    node.start_intake(loop, stop)
    link = _Link()

    # 100 voice chunks (will be mostly rate-dropped) interleaved with 5 SOS.
    for i in range(100):
        node.submit_ble(link, _voice_chunk(2, i % 50))
    for k in range(5):
        node.submit_ble(link, _sos(f"crit-{k}", urgency=5))

    for _ in range(200):
        if sum(1 for a in accepted if a.startswith("crit-")) >= 5:
            break
        await asyncio.sleep(0.005)
    stop.set()
    await asyncio.sleep(0.02)

    crit = sorted(a for a in accepted if a.startswith("crit-"))
    assert crit == ["crit-0", "crit-1", "crit-2", "crit-3", "crit-4"], \
        f"an SOS was dropped by the rate cap: {crit}"
    assert not node.critical_alarm, "critical lane should not have overflowed here"
    print("  ok  test_sos_never_rate_dropped (all", len(crit), "SOS admitted)")


async def _test_malformed_dropped_at_intake() -> None:
    """Undecodable bytes are dropped at classification and never reach a lane/handler."""
    accepted: list[str] = []

    async def on_accept(msg) -> None:
        accepted.append(msg.id)

    node = _make_node(on_accept)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    node.start_intake(loop, stop)
    node.submit_ble(_Link(), b"not-a-valid-envelope")
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.sleep(0.02)
    assert accepted == [], f"malformed frame leaked through: {accepted}"
    print("  ok  test_malformed_dropped_at_intake")


async def _test_classify() -> None:
    """SOS envelope -> critical; voice chunk / non-SOS -> normal."""
    node = _make_node(None)
    sos = env.Envelope(id="s", type="SOS", origin="p1", urgency=1)
    vc = env.VoiceChunk(origin="p2", seq=1, index=0, total=3, payload=b"x")
    delivered = env.Envelope(id="d", type="DELIVERED", origin="p1")
    assert node._is_critical(sos) is True
    assert node._is_critical(vc) is False
    assert node._is_critical(delivered) is False
    print("  ok  test_classify (SOS critical; voice/DELIVERED normal)")


async def main() -> int:
    tests = [_test_classify, _test_sos_first, _test_sos_never_rate_dropped,
             _test_malformed_dropped_at_intake]
    for t in tests:
        await _run(t())
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
