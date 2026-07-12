"""
One GPIO surface, three backends — so the SX1278 driver is byte-for-byte identical on
the Raspberry Pi and on the Arduino UNO Q's Linux side (CONTRACT 1).

`sx127x.py` and `preflight.py` import `GPIO` from here and use the small RPi.GPIO-shaped
API (`setmode/setwarnings/setup/output/input/cleanup` + the BCM/OUT/IN/HIGH/LOW/PUD_DOWN
constants). This module picks whichever backend the board actually has:

  * RPi.GPIO — the Raspberry Pi. Used directly; this is exactly RPi.GPIO.
  * lgpio    — the UNO Q's Debian (or any Pi-5/libgpiod board). Wrapped to look like
               RPi.GPIO. Only needed if a radio is wired to the UNO Q's *Linux* GPIO.
  * none     — no GPIO library present. Import still succeeds (so a serial-modem field
               board, which never touches GPIO, can run), but any real pin call raises a
               clear error rather than a confusing ImportError at startup.

`backend_name()` reports which one is live, so pre-flight can print it and wiring is
never ambiguous.

Licensing: RPi.GPIO (MIT) and lgpio (Unlicense/public-domain) are both permissive
(project rule 1). No vendor SDK internals are reproduced — only the documented public
GPIO calls of each library.
"""
from __future__ import annotations

import os
from typing import Optional


class _NullGPIO:
    """Stand-in used when no GPIO library is installed. Constants exist so
    `setup(pin, GPIO.OUT, initial=GPIO.HIGH)` parses; the actual pin operations raise so
    a misconfigured board fails loudly instead of silently doing nothing."""
    BCM = "BCM"
    OUT = "OUT"
    IN = "IN"
    HIGH = 1
    LOW = 0
    PUD_DOWN = "PUD_DOWN"
    PUD_UP = "PUD_UP"
    PUD_OFF = "PUD_OFF"

    _MSG = ("no GPIO backend is available on this board. Install RPi.GPIO (Raspberry Pi) "
            "or lgpio (UNO Q: `pip install lgpio`). A field board that talks to its radio "
            "through the UNO Q serial modem does not need GPIO at all — use "
            "radios.<node>.transport = \"serial\" and this error will not be reached.")

    # setmode/setwarnings/cleanup are no-ops: a serial-only board calls gpio_init()/
    # gpio_cleanup() unconditionally, and those must not blow up when GPIO is unused.
    def setmode(self, *_a, **_k) -> None: pass
    def setwarnings(self, *_a, **_k) -> None: pass
    def cleanup(self, *_a, **_k) -> None: pass

    def setup(self, *_a, **_k):
        raise RuntimeError(self._MSG)

    def output(self, *_a, **_k):
        raise RuntimeError(self._MSG)

    def input(self, *_a, **_k):
        raise RuntimeError(self._MSG)


class _LgpioGPIO:
    """Adapt the `lgpio` API to the RPi.GPIO calls this codebase makes.

    Only the handful of operations `sx127x.py` needs are mapped: claim a pin as input
    (with pull) or output (with an initial level), read, write, and release. The gpiochip
    defaults to 0 (correct on a Pi and on most single-chip boards) and can be overridden
    with SANKAT_GPIOCHIP if the UNO Q enumerates its header on a different chip.
    """
    BCM = "BCM"
    OUT = "OUT"
    IN = "IN"
    HIGH = 1
    LOW = 0
    PUD_DOWN = "PUD_DOWN"
    PUD_UP = "PUD_UP"
    PUD_OFF = "PUD_OFF"

    def __init__(self, lgpio_mod):
        self._lg = lgpio_mod
        self._chip_num = int(os.environ.get("SANKAT_GPIOCHIP", "0"))
        self._h: Optional[int] = None
        self._claimed: set[int] = set()

    def _chip(self) -> int:
        if self._h is None:
            self._h = self._lg.gpiochip_open(self._chip_num)
        return self._h

    def setmode(self, *_a, **_k) -> None:
        # lgpio addresses lines on a chip directly; there is no BCM/BOARD mode to set.
        pass

    def setwarnings(self, *_a, **_k) -> None:
        pass

    def setup(self, pin, direction, initial=LOW, pull_up_down=None) -> None:
        h = self._chip()
        if pin in self._claimed:
            self._lg.gpio_free(h, pin)
            self._claimed.discard(pin)
        if direction == self.OUT:
            self._lg.gpio_claim_output(h, pin, self.HIGH if initial == self.HIGH else self.LOW)
        else:
            flags = 0
            if pull_up_down == self.PUD_DOWN:
                flags = self._lg.SET_PULL_DOWN
            elif pull_up_down == self.PUD_UP:
                flags = self._lg.SET_PULL_UP
            self._lg.gpio_claim_input(h, pin, flags)
        self._claimed.add(pin)

    def output(self, pin, level) -> None:
        self._lg.gpio_write(self._chip(), pin, self.HIGH if level else self.LOW)

    def input(self, pin) -> int:
        return self._lg.gpio_read(self._chip(), pin)

    def cleanup(self, *_a, **_k) -> None:
        if self._h is None:
            return
        for pin in list(self._claimed):
            try:
                self._lg.gpio_free(self._h, pin)
            except Exception:
                pass
        self._claimed.clear()
        try:
            self._lg.gpiochip_close(self._h)
        except Exception:
            pass
        self._h = None


def _select():
    """Return (GPIO_object, backend_name), preferring a real backend over the null one."""
    try:
        import RPi.GPIO as _rpi  # type: ignore
        return _rpi, "RPi.GPIO"
    except Exception:
        pass
    try:
        import lgpio as _lg  # type: ignore
        return _LgpioGPIO(_lg), "lgpio"
    except Exception:
        pass
    return _NullGPIO(), "none"


GPIO, _BACKEND = _select()


def backend_name() -> str:
    """Which GPIO backend is live: 'RPi.GPIO', 'lgpio', or 'none'."""
    return _BACKEND
