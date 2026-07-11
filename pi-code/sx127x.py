"""
Minimal SX1276/78 (Ra-02) LoRa driver over spidev + RPi.GPIO.

Register names and reset values follow the public Semtech SX1276/77/78/79 datasheet
(rev 7), chapter 4 (LoRa mode registers). No vendor SDK internals are reproduced.

Deliberately raw rather than pulling in Adafruit Blinka: this Pi already has spidev
(MIT) and RPi.GPIO (MIT), and a half-duplex two-radio bridge needs precise control of
mode transitions that the high-level libraries hide.

Threading contract
------------------
Each Radio owns one SpiDev handle and one RLock. `send()` takes the lock, parks the
radio in TX, waits for TxDone, and restores RX-continuous. The RX poller thread reads
DIO0 without the lock and only takes it once the line is high, so a transmit never
races a FIFO read.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import spidev

# GPIO access differs by board: RPi.GPIO on the Raspberry Pi, lgpio/sysfs on the UNO Q's
# Linux side. gpio_compat exposes ONE RPi.GPIO-shaped surface so this driver is identical
# on both tiers (CONTRACT 1). On a Pi with RPi.GPIO installed this is exactly RPi.GPIO.
from gpio_compat import GPIO

# --- LoRa-mode registers (datasheet table 41) --------------------------------
REG_FIFO = 0x00
REG_OP_MODE = 0x01
REG_FRF_MSB = 0x06
REG_PA_CONFIG = 0x09
REG_OCP = 0x0B
REG_LNA = 0x0C
REG_FIFO_ADDR_PTR = 0x0D
REG_FIFO_TX_BASE = 0x0E
REG_FIFO_RX_BASE = 0x0F
REG_FIFO_RX_CURRENT = 0x10
REG_IRQ_FLAGS = 0x12
REG_RX_NB_BYTES = 0x13
REG_PKT_SNR = 0x19
REG_PKT_RSSI = 0x1A
REG_RSSI = 0x1B
REG_HOP_CHANNEL = 0x1C
REG_MODEM_CONFIG1 = 0x1D
REG_MODEM_CONFIG2 = 0x1E
REG_PREAMBLE_MSB = 0x20
REG_PAYLOAD_LENGTH = 0x22
REG_MAX_PAYLOAD = 0x23
REG_MODEM_CONFIG3 = 0x26
REG_DETECT_OPTIMIZE = 0x31
REG_DETECTION_THRESHOLD = 0x37
REG_SYNC_WORD = 0x39
REG_DIO_MAPPING1 = 0x40
REG_VERSION = 0x42
REG_PA_DAC = 0x4D

# RegOpMode
MODE_SLEEP, MODE_STDBY, MODE_TX, MODE_CAD, MODE_RX_CONT = 0x00, 0x01, 0x03, 0x07, 0x05
LONG_RANGE_MODE = 0x80
OPMODE_RESET_VALUE = 0x09  # FSK standby, low-frequency mode — the chip's power-on state

# RegIrqFlags
IRQ_RX_TIMEOUT = 0x80
# A transmit that finishes in less than this fraction of its theoretical time on air
# did not happen. Loose enough for clock jitter, tight enough to catch a dead radio.
MIN_AIRTIME_FRACTION = 0.5

IRQ_RX_DONE = 0x40
IRQ_CRC_ERROR = 0x20
IRQ_TX_DONE = 0x08
IRQ_CAD_DONE = 0x04

# DIO0 mapping (RegDioMapping1 bits 7:6)
DIO0_RX_DONE = 0x00
DIO0_TX_DONE = 0x40
DIO0_CAD_DONE = 0x80

CHIP_VERSION = 0x12  # SX1276/77/78/79

# Bandwidth code -> Hz (RegModemConfig1 bits 7:4)
BANDWIDTHS = {
    7800: 0, 10400: 1, 15600: 2, 20800: 3, 31250: 4,
    41700: 5, 62500: 6, 125000: 7, 250000: 8, 500000: 9,
}

# 433 MHz sits in the chip's low-frequency band, which uses a different RSSI offset
# than the 868/915 band (datasheet §5.5.5).
RSSI_OFFSET_LF = -164
RSSI_OFFSET_HF = -157
HF_BAND_START_HZ = 779_000_000

FXOSC_HZ = 32_000_000
FSTEP = FXOSC_HZ / (1 << 19)  # 61.03515625 Hz per Frf LSB


class LoraError(RuntimeError):
    pass


@dataclass(frozen=True)
class RxPacket:
    """One received LoRa frame plus the physical-layer evidence it really arrived."""
    payload: bytes
    rssi_dbm: int
    snr_db: float
    crc_ok: bool
    t_mono: float


@dataclass(frozen=True)
class LoraConfig:
    frequency_hz: int
    spreading_factor: int
    bandwidth_hz: int
    coding_rate: int
    tx_power_dbm: int
    sync_word: int
    preamble_len: int
    crc: bool
    max_payload: int
    spi_bus: int
    spi_speed_hz: int

    def __post_init__(self) -> None:
        if self.bandwidth_hz not in BANDWIDTHS:
            raise LoraError(f"bandwidth {self.bandwidth_hz} Hz unsupported; pick one of {sorted(BANDWIDTHS)}")
        if not 6 <= self.spreading_factor <= 12:
            raise LoraError("spreading_factor must be 6..12")
        if not 5 <= self.coding_rate <= 8:
            raise LoraError("coding_rate must be 5..8 (meaning 4/5..4/8)")
        if not 2 <= self.tx_power_dbm <= 20:
            raise LoraError("tx_power_dbm must be 2..20 (PA_BOOST)")
        if not 1 <= self.max_payload <= 255:
            raise LoraError("max_payload must be 1..255")

    @property
    def symbol_time_s(self) -> float:
        return (1 << self.spreading_factor) / self.bandwidth_hz

    def airtime_s(self, payload_len: int) -> float:
        """Datasheet §4.1.1.7 time-on-air, explicit header, for logging/pacing."""
        sf, bw, cr = self.spreading_factor, self.bandwidth_hz, self.coding_rate - 4
        ts = self.symbol_time_s
        t_preamble = (self.preamble_len + 4.25) * ts
        low_dr = 1 if ts > 0.016 else 0
        num = 8 * payload_len - 4 * sf + 28 + (16 if self.crc else 0) - 0  # explicit header
        den = 4 * (sf - 2 * low_dr)
        n_payload = 8 + max(0, -(-num // den) * (cr + 4))  # ceil division
        return t_preamble + n_payload * ts


class Radio:
    """One Ra-02 module on a shared SPI bus, addressed by its own chip-select + GPIOs."""

    def __init__(self, name: str, cs: int, rst_gpio: int, dio0_gpio: int, cfg: LoraConfig):
        self.name = name
        self.cs = cs
        self.rst_gpio = rst_gpio
        self.dio0_gpio = dio0_gpio
        self.cfg = cfg

        self._lock = threading.RLock()
        self._tx_active = False
        self._stop = threading.Event()
        self._rx_thread: Optional[threading.Thread] = None
        self._on_receive: Optional[Callable[[RxPacket], None]] = None

        self._spi = spidev.SpiDev()
        self._spi.open(cfg.spi_bus, cs)
        # spidev latches SPI_NO_CS in the kernel across close()/open(): a previous
        # process that set it would leave NSS permanently high and every register
        # would read 0x00. Clear it explicitly rather than trusting the default.
        self._spi.no_cs = False
        self._spi.mode = 0
        self._spi.max_speed_hz = cfg.spi_speed_hz

        GPIO.setup(rst_gpio, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(dio0_gpio, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    # --- raw SPI ------------------------------------------------------------
    def _read(self, addr: int) -> int:
        with self._lock:
            return self._spi.xfer2([addr & 0x7F, 0x00])[1]

    def _write(self, addr: int, value: int) -> None:
        with self._lock:
            self._spi.xfer2([addr | 0x80, value & 0xFF])

    def _read_burst(self, addr: int, n: int) -> bytes:
        with self._lock:
            return bytes(self._spi.xfer2([addr & 0x7F] + [0] * n)[1:])

    def _write_burst(self, addr: int, data: bytes) -> None:
        with self._lock:
            self._spi.xfer2([addr | 0x80] + list(data))

    # --- lifecycle ----------------------------------------------------------
    def reset(self) -> None:
        GPIO.output(self.rst_gpio, GPIO.LOW)
        time.sleep(0.002)
        GPIO.output(self.rst_gpio, GPIO.HIGH)
        time.sleep(0.010)

    def open(self) -> None:
        self.reset()
        version = self._read(REG_VERSION)
        if version != CHIP_VERSION:
            raise LoraError(
                f"radio '{self.name}' (CE{self.cs}): RegVersion=0x{version:02X}, expected 0x12. "
                "Check NSS/SCK/MOSI/MISO wiring and that no other process holds the SPI bus."
            )
        self._set_mode(MODE_SLEEP)  # LoRa bit can only be flipped in sleep
        self._configure()
        self._set_mode(MODE_STDBY)

    def _configure(self) -> None:
        c = self.cfg

        frf = int(round(c.frequency_hz / FSTEP))
        self._write(REG_FRF_MSB + 0, (frf >> 16) & 0xFF)
        self._write(REG_FRF_MSB + 1, (frf >> 8) & 0xFF)
        self._write(REG_FRF_MSB + 2, frf & 0xFF)

        self._set_tx_power(c.tx_power_dbm)
        self._write(REG_OCP, 0x20 | 0x0B)          # over-current protect ~100 mA
        self._write(REG_LNA, 0x23)                 # max LNA gain + boost on

        bw_code = BANDWIDTHS[c.bandwidth_hz]
        self._write(REG_MODEM_CONFIG1, (bw_code << 4) | ((c.coding_rate - 4) << 1))  # explicit header
        self._write(REG_MODEM_CONFIG2, (c.spreading_factor << 4) | (0x04 if c.crc else 0x00))

        # Low-data-rate optimize is mandatory once a symbol exceeds 16 ms, else the
        # link silently fails at SF11/SF12 on narrow bandwidths.
        low_dr = 0x08 if c.symbol_time_s > 0.016 else 0x00
        self._write(REG_MODEM_CONFIG3, low_dr | 0x04)  # + AGC auto-on

        # SF6 is implicit-header-only and needs different detection constants.
        if c.spreading_factor == 6:
            self._write(REG_DETECT_OPTIMIZE, 0xC5)
            self._write(REG_DETECTION_THRESHOLD, 0x0C)
        else:
            self._write(REG_DETECT_OPTIMIZE, 0xC3)
            self._write(REG_DETECTION_THRESHOLD, 0x0A)

        self._write(REG_PREAMBLE_MSB, (c.preamble_len >> 8) & 0xFF)
        self._write(REG_PREAMBLE_MSB + 1, c.preamble_len & 0xFF)
        self._write(REG_SYNC_WORD, c.sync_word & 0xFF)
        self._write(REG_MAX_PAYLOAD, c.max_payload)
        self._write(REG_FIFO_TX_BASE, 0x00)
        self._write(REG_FIFO_RX_BASE, 0x00)

    def _set_tx_power(self, dbm: int) -> None:
        # Ra-02 routes the antenna through PA_BOOST; the RFO pin is not bonded out.
        if dbm > 17:
            self._write(REG_PA_DAC, 0x87)          # +20 dBm mode
            self._write(REG_PA_CONFIG, 0x80 | 0x70 | 0x0F)
        else:
            self._write(REG_PA_DAC, 0x84)
            self._write(REG_PA_CONFIG, 0x80 | 0x70 | ((dbm - 2) & 0x0F))

    def _set_mode(self, mode: int) -> None:
        self._write(REG_OP_MODE, LONG_RANGE_MODE | mode)

    def close(self) -> None:
        self.stop_receiving()
        try:
            self._set_mode(MODE_SLEEP)
        except Exception:
            pass
        self._spi.close()

    # --- measurement --------------------------------------------------------
    @property
    def _rssi_offset(self) -> int:
        return RSSI_OFFSET_HF if self.cfg.frequency_hz >= HF_BAND_START_HZ else RSSI_OFFSET_LF

    def channel_rssi_dbm(self) -> int:
        """Instantaneous RSSI — used for carrier sense before transmitting."""
        return self._rssi_offset + self._read(REG_RSSI)

    def _packet_rssi_dbm(self, snr_db: float) -> int:
        raw = self._read(REG_PKT_RSSI)
        rssi = self._rssi_offset + raw
        # Below the noise floor the reported value needs the SNR correction (§5.5.5).
        return int(rssi + 0.25 * snr_db) if snr_db < 0 else int(rssi)

    def _packet_snr_db(self) -> float:
        raw = self._read(REG_PKT_SNR)
        return ((raw - 256) if raw > 127 else raw) / 4.0

    # --- wiring self-checks (no transmit; safe without an antenna) -----------
    def check_rst_wire(self) -> bool:
        """Write a non-default RegOpMode, pulse RST, confirm the chip reverted.

        Proves the RST line actually reaches the module. A floating RST reads back the
        value we wrote, because nothing reset the chip.
        """
        with self._lock:
            self._write(REG_OP_MODE, LONG_RANGE_MODE | MODE_SLEEP)  # 0x80
            if self._read(REG_OP_MODE) != (LONG_RANGE_MODE | MODE_SLEEP):
                return False
            self.reset()
            reverted = self._read(REG_OP_MODE) == OPMODE_RESET_VALUE
            self._set_mode(MODE_SLEEP)
            self._configure()
            self._set_mode(MODE_STDBY)
            return reverted

    def check_dio0_wire(self, timeout_s: float = 0.5) -> bool:
        """Run a channel-activity-detect and watch DIO0 rise on CadDone.

        CAD is receive-only, so this proves the DIO0 interrupt line without keying the
        PA. Must not be called while the RX thread is running.
        """
        with self._lock:
            self._set_mode(MODE_STDBY)
            self._write(REG_DIO_MAPPING1, DIO0_CAD_DONE)
            self._write(REG_IRQ_FLAGS, 0xFF)
            if GPIO.input(self.dio0_gpio):
                return False  # stuck high before we even started
            self._set_mode(MODE_CAD)
            deadline = time.monotonic() + timeout_s
            rose = False
            while time.monotonic() < deadline:
                if GPIO.input(self.dio0_gpio):
                    rose = True
                    break
                time.sleep(0.0005)
            flags = self._read(REG_IRQ_FLAGS)
            self._write(REG_IRQ_FLAGS, 0xFF)
            self._set_mode(MODE_STDBY)
            return rose and bool(flags & IRQ_CAD_DONE)

    # --- transmit -----------------------------------------------------------
    def op_mode(self) -> int:
        """Raw RegOpMode. Bit 7 is LongRangeMode; the low bits are the mode."""
        with self._lock:
            return self._read(REG_OP_MODE)

    def in_lora_mode(self) -> bool:
        """False if the chip has fallen back to FSK — i.e. it reset behind our back.

        This matters more than it looks. RegIrqFlags (0x12) addresses a *different*
        register in FSK mode, and its bits read as set, so `send()` sees TxDone
        immediately, reports a few tenths of a millisecond of airtime, transmits
        nothing, and returns success. RegVersion still reads 0x12, so pre-flight passes
        too. The only tell is this bit.
        """
        with self._lock:
            return bool(self._read(REG_OP_MODE) & LONG_RANGE_MODE)

    def reinit(self) -> None:
        """Re-run the power-on sequence and resume receiving. For recovering a radio
        that reset itself mid-run."""
        with self._lock:
            self.open()
            self._resume_rx_locked()

    def send(self, payload: bytes, timeout_s: float = 5.0) -> float:
        """Transmit one frame. Returns measured airtime in seconds. Blocks."""
        if not payload:
            raise LoraError("refusing to transmit an empty frame")
        if len(payload) > self.cfg.max_payload:
            raise LoraError(f"frame {len(payload)}B exceeds max_payload {self.cfg.max_payload}B")

        with self._lock:
            if not self.in_lora_mode():
                raise LoraError(
                    f"radio '{self.name}' is no longer in LoRa mode — it reset behind our "
                    "back. Nothing it 'sends' would leave the antenna."
                )
            self._tx_active = True
            try:
                self._set_mode(MODE_STDBY)
                self._write(REG_DIO_MAPPING1, DIO0_TX_DONE)
                self._write(REG_IRQ_FLAGS, 0xFF)
                self._write(REG_FIFO_TX_BASE, 0x00)
                self._write(REG_FIFO_ADDR_PTR, 0x00)
                self._write_burst(REG_FIFO, payload)
                self._write(REG_PAYLOAD_LENGTH, len(payload))

                t0 = time.monotonic()
                self._set_mode(MODE_TX)
                while time.monotonic() - t0 < timeout_s:
                    if self._read(REG_IRQ_FLAGS) & IRQ_TX_DONE:
                        break
                    time.sleep(0.001)
                else:
                    raise LoraError(f"radio '{self.name}': TxDone timeout after {timeout_s}s")
                airtime = time.monotonic() - t0
                self._write(REG_IRQ_FLAGS, 0xFF)

                # Physics check. A frame's time on air is set by SF, bandwidth and length;
                # it cannot come in far under that. If it does, TxDone was already set
                # when we looked, the antenna radiated nothing, and reporting success here
                # would put a fabricated LORA_TX row in the evidence log.
                floor = MIN_AIRTIME_FRACTION * self.cfg.airtime_s(len(payload))
                if airtime < floor:
                    raise LoraError(
                        f"radio '{self.name}': TxDone fired after {airtime * 1000:.1f} ms but "
                        f"{len(payload)} bytes need {self.cfg.airtime_s(len(payload)) * 1000:.0f} ms "
                        "on air. The frame was never transmitted."
                    )
                return airtime
            finally:
                self._tx_active = False
                self._resume_rx_locked()

    # --- receive ------------------------------------------------------------
    def _resume_rx_locked(self) -> None:
        if self._on_receive is None:
            self._set_mode(MODE_STDBY)
            return
        self._write(REG_DIO_MAPPING1, DIO0_RX_DONE)
        self._write(REG_FIFO_RX_BASE, 0x00)
        self._write(REG_FIFO_ADDR_PTR, 0x00)
        self._set_mode(MODE_RX_CONT)

    def start_receiving(self, on_receive: Callable[[RxPacket], None]) -> None:
        self._on_receive = on_receive
        with self._lock:
            self._write(REG_IRQ_FLAGS, 0xFF)
            self._resume_rx_locked()
        self._stop.clear()
        self._rx_thread = threading.Thread(target=self._rx_loop, name=f"rx-{self.name}", daemon=True)
        self._rx_thread.start()

    def stop_receiving(self) -> None:
        self._stop.set()
        if self._rx_thread is not None:
            self._rx_thread.join(timeout=2.0)
            self._rx_thread = None
        self._on_receive = None

    def _rx_loop(self) -> None:
        while not self._stop.is_set():
            # Poll the pin lock-free; only contend for SPI once there's really an IRQ.
            # Skip while a transmit owns the radio — DIO0 means TxDone there, not RxDone.
            if self._tx_active or not GPIO.input(self.dio0_gpio):
                time.sleep(0.001)
                continue
            pkt = self._drain_rx()
            if pkt is not None and self._on_receive is not None:
                try:
                    self._on_receive(pkt)
                except Exception:  # a bad handler must never kill the radio thread
                    pass

    def _drain_rx(self) -> Optional[RxPacket]:
        with self._lock:
            if self._tx_active:
                return None
            # In FSK (i.e. after the chip reset itself) 0x12 is a different register and
            # reads with bits set, so RxDone looks true and we would "receive" a frame of
            # FIFO garbage. One extra SPI read, only once DIO0 has actually risen.
            if not self._read(REG_OP_MODE) & LONG_RANGE_MODE:
                return None
            flags = self._read(REG_IRQ_FLAGS)
            if not flags & IRQ_RX_DONE:
                self._write(REG_IRQ_FLAGS, 0xFF)
                return None

            t_mono = time.monotonic()
            crc_error = bool(flags & IRQ_CRC_ERROR)
            snr = self._packet_snr_db()
            rssi = self._packet_rssi_dbm(snr)

            n = self._read(REG_RX_NB_BYTES)
            self._write(REG_FIFO_ADDR_PTR, self._read(REG_FIFO_RX_CURRENT))
            payload = self._read_burst(REG_FIFO, n)

            # In explicit-header mode the sender advertises whether it appended a CRC.
            # A frame with no CRC at all cannot be trusted when we asked for one.
            crc_present = bool(self._read(REG_HOP_CHANNEL) & 0x40)
            crc_ok = (not crc_error) and (crc_present or not self.cfg.crc)

            self._write(REG_IRQ_FLAGS, 0xFF)
            self._resume_rx_locked()
            return RxPacket(payload=payload, rssi_dbm=rssi, snr_db=snr, crc_ok=crc_ok, t_mono=t_mono)


def gpio_init() -> None:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)


def gpio_cleanup() -> None:
    GPIO.cleanup()
