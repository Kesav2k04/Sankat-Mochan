"""
Router-Bridge LoRa transport — the field radio driven by the UNO Q's own MCU.

Single-board successor to `serial_radio.py`. On the Raspberry Pi the LoRa modem was a
*separate* Arduino on USB, reachable as a raw serial port (`SerialRadio`). On the Arduino
UNO Q the modem is the board's **own** STM32, and Linux talks to it not over a tty but
over the **Router Bridge**: an RPC channel multiplexed by the always-running
`arduino-router` service on the unix socket `/var/run/arduino-router.sock`.

`BridgeRadio` is a drop-in for `sx127x.Radio` / `SerialRadio`: it presents the SAME
surface the gateway, `LoRaLink` and the radio watchdog use (`open`, `send`,
`start_receiving`, `stop_receiving`, `op_mode`, `in_lora_mode`, `reinit`,
`channel_rssi_dbm`, `close`, and the `rst_gpio`/`name`/`cfg` attributes), so nothing
above the transport layer changes.

RPC contract — matches the sketch in `../sketch/sketch.ino`. Payloads are raw bytes
(MessagePack bin), so a full frame needs no hex doubling:

    host -> MCU (call):   lora_tx(bytes) -> int airtime_ms  (negative = failure)
                          lora_ping()    -> "<freq> <sf> <bw> <cr> <sync-hex> <ok|down>"
    MCU  -> host (notify): lora_rx(bytes payload, int rssi, float snr)

Every inbound frame is still untrusted (CLAUDE.md #8); this layer only moves bytes.
Validation/dedup/size-capping happen unchanged in `envelope.py` / `node.py` downstream.

Dependency: msgpack (via the vendored `bridge_client`) — permissive (project rule 1).
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from sx127x import (
    LONG_RANGE_MODE,
    MODE_RX_CONT,
    LoraConfig,
    LoraError,
    RxPacket,
)

DEFAULT_ROUTER_SOCKET = "/var/run/arduino-router.sock"

# The MCU's RPC request buffer is DEFAULT_RPC_BUFFER_SIZE (256 B) and RPClite *cleanly
# rejects* anything larger (it never truncates — see the sketch's SIZE NOTE). One
# `lora_tx(bin)` call costs ~18 B of MessagePack framing, so the largest payload that
# fits in a single RPC is ~238 B. We cap a little below that and fail fast with a clear
# error, rather than letting an oversized call sit until it times out. Voice chunks
# (217 B) and every normal SOS text envelope fit comfortably.
BRIDGE_TX_SAFE_MAX = 234


class BridgeRadio:
    """A LoRa radio reached over the Router Bridge to the UNO Q's on-board modem sketch.

    Mirrors the parts of `sx127x.Radio` the rest of the gateway relies on. The real
    SX1278 register work happens on the STM32; here we only marshal RPC calls, register
    the receive callback, and hand frames up to the node as `RxPacket`s.
    """

    def __init__(self, name: str, cfg: LoraConfig, logger, *,
                 socket_path: str = DEFAULT_ROUTER_SOCKET, boot_timeout_s: float = 8.0):
        self.name = name
        self.cfg = cfg
        self._log = logger
        self._socket_path = socket_path
        self._boot_timeout_s = boot_timeout_s
        # The watchdog prints this on an unrecoverable radio; -1 flags "no GPIO here,
        # it's a bridge modem" so the message can't send anyone chasing a wire.
        self.rst_gpio = -1

        self._conn = None                       # a bridge_client._ClientServer
        self._on_receive: Optional[Callable[[RxPacket], None]] = None
        self._lock = threading.Lock()

    # --- lifecycle ----------------------------------------------------------
    def open(self) -> None:
        """Connect to the router socket and confirm the MCU modem is alive and configured.

        The router service is always up, but the MCU sketch may still be booting (or not
        yet flashed). We retry `lora_ping` until the boot timeout; if nothing answers we
        refuse to start with a plain-language error.
        """
        from bridge_client import _ClientServer  # vendored, msgpack-only

        conn = _ClientServer(f"unix://{self._socket_path}")
        conn.start()                            # opens the socket + read/reconnect loop
        self._conn = conn

        deadline = time.monotonic() + self._boot_timeout_s
        banner: Optional[str] = None
        last_err: Optional[Exception] = None
        while time.monotonic() < deadline:
            try:
                banner = conn.call("lora_ping", timeout=2)
                if banner:
                    break
            except Exception as e:              # ValueError (no such method yet) / TimeoutError
                last_err = e
            time.sleep(0.3)

        if not banner:
            self.close()
            hint = f" (last error: {last_err})" if last_err else ""
            raise LoraError(
                f"radio '{self.name}': the UNO Q LoRa modem did not answer over the Router "
                f"Bridge on {self._socket_path}{hint}. Is the sketch flashed and the app "
                "running (arduino-app-cli app start ~/ArduinoApps/sankat), and is the "
                "arduino-router service up?"
            )
        self._verify_banner(str(banner))

    def _verify_banner(self, banner: str) -> None:
        """Warn (not fail) if the modem's compiled settings differ from ours, or if its
        radio came up 'down'. Both radios must agree on freq/SF/BW/CR/sync to hear each
        other."""
        self._log.info("[%s] bridge LoRa modem ready (%s)", self.name, banner)
        parts = banner.split()
        # "<freq> <sf> <bw> <cr> <sync-hex> <ok|down>"
        if len(parts) < 6:
            self._log.warning("[%s] could not parse modem banner %r — check the sketch",
                              self.name, banner)
            return
        freq, sf, bw, cr, sync, state = parts[:6]
        if state != "ok":
            self._log.warning(
                "[%s] modem reports its radio is '%s' — the SX1278 did not initialise. "
                "Check SS/RST/DIO0 wiring and 3V3 power; TX/RX will fail until fixed.",
                self.name, state)
        try:
            want = (
                (int(freq), self.cfg.frequency_hz, "frequency_hz"),
                (int(sf), self.cfg.spreading_factor, "spreading_factor"),
                (int(bw), self.cfg.bandwidth_hz, "bandwidth_hz"),
                (int(cr), self.cfg.coding_rate, "coding_rate"),
                (int(sync, 16), self.cfg.sync_word, "sync_word"),
            )
            for got, expect, label in want:
                if got != expect:
                    self._log.warning(
                        "[%s] modem %s=%s but this board's config says %s — the two radios "
                        "will NOT hear each other. Reconcile the sketch's #defines with "
                        "pi-code config.", self.name, label, got, expect)
        except ValueError:
            self._log.warning("[%s] could not parse modem banner %r — check the sketch",
                              self.name, banner)

    def close(self) -> None:
        self.stop_receiving()
        conn = self._conn
        self._conn = None
        if conn is not None:
            try:
                conn.stop()
            except Exception:
                pass

    def reinit(self) -> None:
        """Recover a modem that stopped answering: drop the connection and reconnect, then
        resume RX. Mirrors `Radio.reinit()` so the radio watchdog treats all transports
        identically."""
        cb = self._on_receive
        self.close()
        self.open()
        if cb is not None:
            self.start_receiving(cb)

    # --- receive ------------------------------------------------------------
    def start_receiving(self, on_receive: Callable[[RxPacket], None]) -> None:
        """Register `lora_rx` so the router routes the MCU's inbound-frame notifications
        to us. The bridge's own read thread invokes the handler; no thread to manage here."""
        if self._conn is None:
            raise LoraError(f"radio '{self.name}': bridge is not open")
        self._on_receive = on_receive
        self._conn.provide("lora_rx", self._handle_rx)

    def stop_receiving(self) -> None:
        conn = self._conn
        if conn is not None:
            try:
                conn.unprovide("lora_rx")
            except Exception:
                pass
        self._on_receive = None

    def _handle_rx(self, payload, rssi, snr) -> None:
        cb = self._on_receive
        if cb is None:
            return
        # msgpack bin -> bytes; guard against odd types coming off an untrusted link.
        if isinstance(payload, (bytes, bytearray)):
            payload = bytes(payload)
        elif isinstance(payload, str):
            payload = payload.encode("latin-1", "ignore")
        else:
            self._log.debug("[%s] dropping RX with non-bytes payload %r", self.name, type(payload))
            return
        if not payload:
            return
        try:
            rssi_i = int(rssi)
            snr_f = float(snr)
        except (TypeError, ValueError):
            self._log.debug("[%s] undecodable RX metadata rssi=%r snr=%r", self.name, rssi, snr)
            return
        # CRC was verified on the STM32 (the LoRa library drops CRC-failed frames), so a
        # frame that reached us is known-good at the physical layer.
        pkt = RxPacket(payload=payload, rssi_dbm=rssi_i, snr_db=snr_f,
                       crc_ok=True, t_mono=time.monotonic())
        try:
            cb(pkt)
        except Exception:  # a bad handler must never kill the bridge read thread
            pass

    # --- transmit -----------------------------------------------------------
    def send(self, payload: bytes, timeout_s: float = 5.0) -> float:
        """Transmit one frame; block until the modem confirms. Returns airtime in seconds.
        Raises LoraError on failure, matching `sx127x.Radio.send`."""
        if not payload:
            raise LoraError("refusing to transmit an empty frame")
        if len(payload) > self.cfg.max_payload:
            raise LoraError(
                f"frame {len(payload)}B exceeds max_payload {self.cfg.max_payload}B")
        if len(payload) > BRIDGE_TX_SAFE_MAX:
            # Fail fast and loud rather than let an oversized RPC time out on the MCU.
            raise LoraError(
                f"radio '{self.name}': frame {len(payload)}B exceeds the Router-Bridge "
                f"single-call limit of {BRIDGE_TX_SAFE_MAX}B (the MCU's 256B RPC buffer). "
                "Shorten the message, or add fragmentation to the modem protocol.")
        if self._conn is None:
            raise LoraError(f"radio '{self.name}': bridge is not open")

        with self._lock:
            try:
                # timeout budget a hair above the caller's, so the bridge times out first.
                airtime_ms = self._conn.call("lora_tx", bytes(payload),
                                             timeout=max(1, int(timeout_s) + 1))
            except TimeoutError as e:
                raise LoraError(
                    f"radio '{self.name}': no transmit confirmation from the modem "
                    f"within {timeout_s}s") from e
            except Exception as e:
                raise LoraError(f"radio '{self.name}': transmit RPC failed: {e}") from e

        if not isinstance(airtime_ms, int):
            raise LoraError(
                f"radio '{self.name}': modem returned a non-integer airtime {airtime_ms!r}")
        if airtime_ms < 0:
            reason = {-1: "radio not initialised", -2: "bad frame length",
                      -3: "radio busy"}.get(airtime_ms, f"code {airtime_ms}")
            raise LoraError(f"radio '{self.name}': modem refused the frame ({reason})")
        return airtime_ms / 1000.0

    # --- health / carrier sense ---------------------------------------------
    def channel_rssi_dbm(self) -> int:
        """Instantaneous channel RSSI for CSMA. The modem sketch does not expose the
        SX1278's live RSSI register, so we report a level below any sane threshold — the
        channel reads as clear and `LoRaLink` sends without waiting. With a single field
        radio this is correct (there is no second local transmitter to collide with)."""
        return -120

    def _ping(self) -> bool:
        conn = self._conn
        if conn is None:
            return False
        try:
            banner = conn.call("lora_ping", timeout=2)
        except Exception:
            return False
        return bool(banner)

    def op_mode(self) -> int:
        """Liveness, shaped like `Radio.op_mode()` for the radio watchdog. Bit 7
        (LONG_RANGE_MODE) set means "healthy and in LoRa mode". We prove that by pinging
        the modem over the bridge: if the STM32 answers, its LoRa loop is running; if not,
        the watchdog calls reinit() and we reconnect."""
        if self._conn is None:
            return 0
        return (LONG_RANGE_MODE | MODE_RX_CONT) if self._ping() else 0

    def in_lora_mode(self) -> bool:
        return bool(self.op_mode() & LONG_RANGE_MODE)
