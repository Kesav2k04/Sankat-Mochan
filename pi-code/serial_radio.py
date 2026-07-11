"""
Serial-backed LoRa transport — the field radio driven by the Arduino UNO Q.

When both Ra-02 radios lived on the Raspberry Pi, `sx127x.Radio` drove each one
directly over SPI. Now the field radio has moved to the UNO Q, whose STM32 side runs
`arduino-unoq/lora_modem` and exposes the radio over a serial link. `SerialRadio` is a
drop-in for `sx127x.Radio`: it presents the SAME surface the gateway, `LoRaLink` and the
radio watchdog already use (`open`, `send`, `start_receiving`, `op_mode`, `reinit`,
`channel_rssi_dbm`, `close`), so nothing above the transport layer changes. The mesh
therefore behaves exactly as it did with two radios on one Pi.

Line protocol (see the sketch header for the authoritative copy). Payloads are hex so a
line can never carry a raw newline; the UNO Q Linux host is the initiator:

    host  -> modem :  "T <hex>"  transmit        |  "P"  ping
    modem -> host  :  "R <hex> <rssi> <snr>"  a frame arrived (CRC already good)
                      "K <ms>"  transmit done   |  "E <reason>"  transmit failed
                      "Y"  pong                 |  "I ..."  boot banner
                      "# ..."  human log (ignored)

Every inbound frame is still untrusted (CLAUDE.md #8); this layer only moves bytes.
Validation/dedup/size-capping happen unchanged in `envelope.py` / `node.py` downstream.

Dependency: pyserial (`import serial`) — BSD-3-Clause, permissive (project rule 1).
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional

# pyserial imports as `serial`. Import lazily-friendly: a clear message beats an
# ImportError traceback if the field board is missing the dep (rule 10).
try:
    import serial  # type: ignore
except ImportError:  # pragma: no cover - environment-dependent
    serial = None  # noqa: N816

from sx127x import (
    LONG_RANGE_MODE,
    MODE_RX_CONT,
    LoraConfig,
    LoraError,
    RxPacket,
)


class SerialRadio:
    """A LoRa radio reached over a serial line to the UNO Q modem sketch.

    Mirrors the parts of `sx127x.Radio` the rest of the gateway relies on. The heavy
    lifting (real SX1278 register work) happens in the Arduino sketch; here we only
    frame lines, track liveness, and hand received frames to the node as `RxPacket`s.
    """

    def __init__(self, name: str, cfg: LoraConfig, port: str, baud: int,
                 logger, *, boot_timeout_s: float = 5.0):
        if serial is None:
            raise LoraError(
                "pyserial is not installed — the serial LoRa transport needs it. "
                "Install it with:  ../.venv/bin/pip install pyserial"
            )
        self.name = name
        self.cfg = cfg
        self.port = port
        self.baud = int(baud)
        self._log = logger
        self._boot_timeout_s = boot_timeout_s
        # The watchdog prints this on an unrecoverable radio; -1 flags "no GPIO here,
        # it's a serial modem" so the message can't send anyone chasing a wire.
        self.rst_gpio = -1

        self._ser: "Optional[serial.Serial]" = None
        self._io_lock = threading.Lock()      # serialises writes + request/response
        self._resp_q: "queue.Queue[str]" = queue.Queue()
        self._on_receive: Optional[Callable[[RxPacket], None]] = None
        self._reader: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_line_mono = 0.0

    # --- lifecycle ----------------------------------------------------------
    def open(self) -> None:
        """Open the serial port and confirm the modem is alive and correctly configured.

        Opening the port may pulse DTR and reset the STM32, so we first watch for its
        boot banner ("I ..."); if we attached after boot instead, we fall back to a ping.
        Either way, if nothing answers we refuse to start with a plain-language error.
        """
        assert serial is not None
        self._ser = serial.Serial(self.port, self.baud, timeout=0.2)
        # Give a board that resets-on-open time to boot before we talk to it.
        deadline = time.monotonic() + self._boot_timeout_s
        banner: Optional[str] = None
        while time.monotonic() < deadline:
            line = self._read_line_blocking(deadline)
            if line is None:
                break
            if line.startswith("I "):
                banner = line
                break
            # "# LoRa init FAILED..." etc. — surface it, keep waiting for a verdict.
            if line.startswith("#"):
                self._log.info("[%s] modem: %s", self.name, line[1:].strip())

        if banner is None:
            # Attached after the banner already scrolled past — ping instead.
            if not self._ping_locked_open():
                self._ser.close()
                self._ser = None
                raise LoraError(
                    f"radio '{self.name}': the modem on {self.port} did not respond. "
                    "Is the UNO Q sketch flashed, is this the right serial device, and "
                    "is anything else (e.g. the Arduino IDE Serial Monitor) holding the port?"
                )
            self._log.info("[%s] serial LoRa modem on %s answered a ping", self.name, self.port)
        else:
            self._verify_banner(banner)

    def _verify_banner(self, banner: str) -> None:
        """Warn (not fail) if the modem's compiled settings differ from ours. Both radios
        must agree on freq/SF/BW/CR/sync or they cannot hear each other."""
        self._log.info("[%s] serial LoRa modem ready on %s (%s)", self.name, self.port, banner)
        try:
            _, freq, sf, bw, cr, sync = banner.split()
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
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def reinit(self) -> None:
        """Recover a modem that stopped answering: reopen the port and resume RX. Mirrors
        `Radio.reinit()` so the radio watchdog can treat both transports identically."""
        cb = self._on_receive
        self.close()
        self._stop.clear()
        self.open()
        if cb is not None:
            self.start_receiving(cb)

    # --- receive ------------------------------------------------------------
    def start_receiving(self, on_receive: Callable[[RxPacket], None]) -> None:
        self._on_receive = on_receive
        self._stop.clear()
        self._reader = threading.Thread(target=self._reader_loop,
                                        name=f"serial-rx-{self.name}", daemon=True)
        self._reader.start()

    def stop_receiving(self) -> None:
        self._stop.set()
        if self._reader is not None:
            self._reader.join(timeout=2.0)
            self._reader = None
        self._on_receive = None

    def _reader_loop(self) -> None:
        """Continuously read lines. RX frames go to the node callback; command replies
        (K/E/Y/I) go to the response queue for send()/ping() to pick up."""
        buf = bytearray()
        while not self._stop.is_set():
            ser = self._ser
            if ser is None:
                time.sleep(0.05)
                continue
            try:
                data = ser.read(256)
            except Exception as e:
                self._log.error("[%s] serial read error: %s: %s",
                                self.name, type(e).__name__, e)
                time.sleep(0.1)
                continue
            if not data:
                continue
            buf.extend(data)
            while b"\n" in buf:
                line, _, rest = buf.partition(b"\n")
                del buf[:]
                buf.extend(rest)
                self._dispatch(line.decode("ascii", "replace").strip())

    def _dispatch(self, line: str) -> None:
        if not line:
            return
        self._last_line_mono = time.monotonic()
        tag = line[0]
        if tag == "R":
            self._handle_rx(line)
        elif tag in ("K", "E", "Y", "I"):
            self._resp_q.put(line)
        elif tag == "#":
            self._log.debug("[%s] modem: %s", self.name, line[1:].strip())
        # anything else: ignore (serial noise); env.decode would drop it anyway

    def _handle_rx(self, line: str) -> None:
        cb = self._on_receive
        if cb is None:
            return
        parts = line.split()
        # "R <hex> <rssi> <snr>"
        if len(parts) != 4:
            self._log.debug("[%s] malformed RX line: %r", self.name, line)
            return
        try:
            payload = bytes.fromhex(parts[1])
            rssi = int(float(parts[2]))
            snr = float(parts[3])
        except ValueError:
            self._log.debug("[%s] undecodable RX line: %r", self.name, line)
            return
        if not payload:
            return
        # CRC was verified on the STM32 (the LoRa library drops CRC-failed frames), so a
        # frame that reached us is known-good at the physical layer.
        pkt = RxPacket(payload=payload, rssi_dbm=rssi, snr_db=snr,
                       crc_ok=True, t_mono=time.monotonic())
        try:
            cb(pkt)
        except Exception:  # a bad handler must never kill the reader thread
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
        if self._ser is None:
            raise LoraError(f"radio '{self.name}': serial port is not open")

        line = "T " + payload.hex() + "\n"
        with self._io_lock:
            self._drain_responses()
            self._ser.write(line.encode("ascii"))
            self._ser.flush()
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                try:
                    resp = self._resp_q.get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if resp.startswith("K"):
                    parts = resp.split()
                    ms = float(parts[1]) if len(parts) > 1 else 0.0
                    return ms / 1000.0
                if resp.startswith("E"):
                    reason = resp[1:].strip() or "unknown"
                    raise LoraError(f"radio '{self.name}': modem refused the frame ({reason})")
                # a stray Y/I between request and reply — ignore and keep waiting
        raise LoraError(
            f"radio '{self.name}': no transmit confirmation from the modem within {timeout_s}s")

    # --- health / carrier sense ---------------------------------------------
    def channel_rssi_dbm(self) -> int:
        """Instantaneous channel RSSI for CSMA. The modem sketch does not expose the
        SX1278's live RSSI register, so we report a level below any sane threshold — the
        channel reads as clear and `LoRaLink` sends without waiting. With a single field
        radio this is correct (there is no second local transmitter to collide with)."""
        return -120

    def _ping_locked_open(self) -> bool:
        """Ping while the reader thread is NOT running yet (used inside open())."""
        assert self._ser is not None
        self._ser.write(b"P\n")
        self._ser.flush()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            line = self._read_line_blocking(deadline)
            if line is None:
                break
            if line.startswith("Y"):
                return True
        return False

    def _ping(self) -> bool:
        """Ping while the reader thread IS running (used by op_mode())."""
        if self._ser is None:
            return False
        with self._io_lock:
            self._drain_responses()
            try:
                self._ser.write(b"P\n")
                self._ser.flush()
            except Exception:
                return False
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                try:
                    resp = self._resp_q.get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if resp.startswith("Y"):
                    return True
        return False

    def op_mode(self) -> int:
        """Liveness, shaped like `Radio.op_mode()` for the radio watchdog. Bit 7
        (LONG_RANGE_MODE) set means "healthy and in LoRa mode". We prove that by pinging
        the modem: if it answers, the STM32 is running its LoRa loop; if not, the watchdog
        will call reinit() and we reopen the port."""
        if self._ser is None:
            return 0
        return (LONG_RANGE_MODE | MODE_RX_CONT) if self._ping() else 0

    def in_lora_mode(self) -> bool:
        return bool(self.op_mode() & LONG_RANGE_MODE)

    # --- helpers ------------------------------------------------------------
    def _drain_responses(self) -> None:
        try:
            while True:
                self._resp_q.get_nowait()
        except queue.Empty:
            pass

    def _read_line_blocking(self, deadline: float) -> Optional[str]:
        """Read one line directly from the port (only safe when the reader thread is not
        running — i.e. during open()/handshake). Returns None on timeout."""
        assert self._ser is not None
        buf = bytearray()
        while time.monotonic() < deadline:
            data = self._ser.read(64)
            if not data:
                if buf:
                    continue
                return None
            buf.extend(data)
            if b"\n" in buf:
                line, _, _ = buf.partition(b"\n")
                return line.decode("ascii", "replace").strip()
        return None
