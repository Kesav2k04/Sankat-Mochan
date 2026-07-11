#!/usr/bin/env python3
"""
Pre-flight: everything that must be true before the gateway can work.

Checks the config, the Python deps, and then the radios for real. What "the radios"
means depends on each node's transport:

  * spi    — the Raspberry Pi gateway: SPI device nodes, group access, chip ID,
             MOSI/MISO write-read-back, the RST wire and the DIO0 interrupt wire.
             No transmit, so it is safe with or without antennas.
  * serial — the Arduino UNO Q field modem: the serial device exists and the modem
             answers (boot banner / ping) with settings that match this config.

Exit 0 = go. Exit 1 = something is wrong, and it says which and how to fix it.
"""
from __future__ import annotations

import grp
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELLOW = DIM = RESET = ""

results: List[Tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "", fix: str = "") -> bool:
    results.append((label, ok, fix))
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    line = f"  [{mark}] {label}"
    if detail:
        line += f" {DIM}— {detail}{RESET}"
    print(line)
    if not ok and fix:
        print(f"         {YELLOW}fix:{RESET} {fix}")
    return ok


def _active_nodes(cfg):
    return list(cfg.get("run", {}).get("nodes", ["field", "gateway"]))


def _transport(cfg, node) -> str:
    return cfg["radios"][node].get("transport", "spi")


def _has(cfg, transport: str) -> bool:
    return any(_transport(cfg, n) == transport for n in _active_nodes(cfg))


def check_config():
    try:
        import config as c
        cfg = c.load()
        lc = c.lora_config(cfg)
    except Exception as e:
        record("config loads and validates", False, str(e),
               "check pi-code/config.json and any SANKAT_* env vars")
        return None
    record("config loads and validates", True,
           f"{lc.frequency_hz/1e6:.3f} MHz SF{lc.spreading_factor} "
           f"BW{lc.bandwidth_hz//1000}k {lc.tx_power_dbm} dBm · "
           f"nodes: {', '.join(_active_nodes(cfg))}")
    return cfg


def check_deps(cfg) -> bool:
    # Base deps everywhere; then the transport-specific ones, so a serial-only field
    # board is not failed for lacking spidev, and a Pi is not failed for lacking pyserial.
    needed = ["bleak", "requests"]
    if _has(cfg, "spi"):
        needed.append("spidev")
    if _has(cfg, "serial"):
        needed.append("serial")   # pyserial imports as `serial`
    if _has(cfg, "bridge"):
        needed.append("msgpack")  # the vendored Router-Bridge client speaks MessagePack-RPC
    missing = []
    for mod in needed:
        try:
            __import__(mod)
        except ImportError:
            missing.append("pyserial" if mod == "serial" else mod)
    ok = record(
        "python deps installed", not missing,
        ", ".join("pyserial" if m == "serial" else m for m in needed)
        if not missing else f"missing: {', '.join(missing)}",
        "run.sh recreates the venv: rm -rf ../.venv && ./run.sh check",
    )

    # GPIO is only needed to drive a radio over SPI. A serial-only field board never
    # touches GPIO, so don't fail it for a missing backend.
    if not _has(cfg, "spi"):
        gpio_ok = record("gpio backend", True, "not required (radio is off-SPI: serial/bridge)")
    else:
        try:
            import gpio_compat
            gpio_ok = record("gpio backend available", True, gpio_compat.backend_name())
        except Exception as e:
            gpio_ok = record("gpio backend available", False, str(e),
                             "Pi: ensure RPi.GPIO is installed. UNO Q: `pip install lgpio`.")
    return ok and gpio_ok


def check_spi_nodes(cfg) -> bool:
    spi_nodes = [n for n in _active_nodes(cfg) if _transport(cfg, n) == "spi"]
    if not spi_nodes:
        return record("SPI device nodes present", True, "no SPI radios (radio reached off-board)")
    bus = cfg["lora"]["spi"]["bus"]
    needed = [f"/dev/spidev{bus}.{cfg['radios'][n]['cs']}" for n in spi_nodes]
    missing = [p for p in needed if not Path(p).exists()]
    return record(
        "SPI device nodes present", not missing,
        " ".join(needed) if not missing else f"missing: {' '.join(missing)}",
        "sudo raspi-config nonint do_spi 0 && sudo reboot",
    )


def check_groups(cfg) -> bool:
    if not _has(cfg, "spi"):
        return record("device access", True, "no SPI radios — group check not applicable")
    if os.geteuid() == 0:
        return record("user in spi + gpio groups", True, "running as root")
    # The 'spi'/'gpio' groups are a Raspberry Pi OS convention. On other Debian boards the
    # device nodes may be owned by other groups, so don't hard-fail there — a real
    # permission problem still surfaces when we actually open the SPI device below.
    try:
        import gpio_compat
        is_pi = gpio_compat.backend_name().startswith("RPi")
    except Exception:
        is_pi = False
    mine = {grp.getgrgid(g).gr_name for g in os.getgroups()}
    missing = {"spi", "gpio"} - mine
    if not is_pi:
        return record("device access", True,
                      "non-Pi board — group check skipped; access is verified by opening the "
                      "radio below")
    return record("user in spi + gpio groups", not missing,
                  "spi, gpio" if not missing else f"missing: {', '.join(sorted(missing))}",
                  f"sudo usermod -aG {','.join(sorted(missing))} $USER  # then log out and back in")


def check_bluetooth(cfg) -> bool:
    if not cfg["ble"]["enabled"]:
        return record("bluetooth adapter", True, "ble.enabled=false, skipped")
    adapter = Path("/sys/class/bluetooth/hci0").exists()
    disable_hint = ("run the LoRa tier alone with SANKAT_BLE__ENABLED=false, or use the "
                    "field_beacon sketch (no BLE needed at all)")
    # rfkill is the nicest way to read the block state, but it is not installed on every
    # board (e.g. the UNO Q). If it is missing, fall back to just checking the adapter
    # exists — bleak will surface any real Bluetooth problem when it actually scans.
    try:
        out = subprocess.run(["rfkill", "list", "bluetooth"], capture_output=True, text=True, timeout=5).stdout
    except FileNotFoundError:
        return record("bluetooth adapter", adapter,
                      "hci0 present (rfkill not installed — could not check block state)"
                      if adapter else "no hci0 and no rfkill",
                      "" if adapter else disable_hint)
    except Exception as e:
        return record("bluetooth adapter", False, str(e), "is `rfkill` installed?")
    if not out.strip():
        return record("bluetooth adapter", adapter, "hci0 present" if adapter else "no adapter found",
                      "" if adapter else "check the board's onboard BT, or " + disable_hint)
    if "Soft blocked: yes" in out:
        return record("bluetooth adapter", False, "soft-blocked",
                      "sudo rfkill unblock bluetooth   (run.sh does this for you)")
    if "Hard blocked: yes" in out:
        return record("bluetooth adapter", False, "hard-blocked", "check a physical switch / firmware")
    return record("bluetooth adapter", adapter, "hci0 unblocked" if adapter else "hci0 absent",
                  "sudo hciconfig hci0 up")


def check_serial_modem(cfg, name) -> bool:
    """Open the UNO Q LoRa modem and confirm it answers with matching settings."""
    import config as c
    r = cfg["radios"][name]
    port = r["serial_port"]
    label = f"radio {name} (serial modem on {port})"
    if not Path(port).exists():
        return record(
            label, False, f"{port} not found",
            "flash arduino-unoq/lora_modem to the UNO Q, then set "
            f"radios.{name}.serial_port to its device (try: ls /dev/ttyACM* /dev/ttyUSB*)")
    try:
        from serial_radio import SerialRadio
        radio = SerialRadio(name, c.lora_config(cfg), port,
                            r.get("serial_baud", 115200), logging.getLogger("preflight"))
        radio.open()
        radio.close()
    except Exception as e:
        return record(label, False, str(e),
                      "is the sketch flashed, and is the port free (close the Arduino "
                      "IDE Serial Monitor)?")
    return record(label, True, "modem responding")


def check_bridge_modem(cfg, name) -> bool:
    """Confirm the UNO Q's on-board LoRa modem answers over the Router Bridge."""
    import config as c
    r = cfg["radios"][name]
    sock = r.get("socket_path", "/var/run/arduino-router.sock")
    label = f"radio {name} (bridge modem on {sock})"
    if not Path(sock).exists():
        return record(
            label, False, f"{sock} not found",
            "the arduino-router service is not running — is this an Arduino UNO Q with "
            "the app framework up? (systemctl status arduino-router)")
    try:
        from bridge_radio import BridgeRadio
        radio = BridgeRadio(name, c.lora_config(cfg), logging.getLogger("preflight"),
                            socket_path=sock, boot_timeout_s=8.0)
        radio.open()
        radio.close()
    except Exception as e:
        return record(label, False, str(e),
                      "flash the modem sketch and start the app: "
                      "arduino-app-cli app start ~/ArduinoApps/sankat  (then re-run). "
                      "Check the MCU with: arduino-app-cli monitor")
    return record(label, True, "modem responding over the bridge")


def check_radios(cfg) -> bool:
    import config as c
    active = _active_nodes(cfg)
    all_ok = True

    # SPI radios need the GPIO subsystem up; serial radios do not.
    spi_nodes = [n for n in active if _transport(cfg, n) == "spi"]
    if spi_nodes:
        from sx127x import Radio, gpio_cleanup, gpio_init
        lora_cfg = c.lora_config(cfg)
        gpio_init()
        radios = []
        try:
            for name in spi_nodes:
                r = cfg["radios"][name]
                label = f"radio {name} (CE{r['cs']} rst=GPIO{r['rst_gpio']} dio0=GPIO{r['dio0_gpio']})"
                try:
                    radio = Radio(name, r["cs"], r["rst_gpio"], r["dio0_gpio"], lora_cfg)
                    radios.append(radio)
                    radio.open()
                except Exception as e:
                    all_ok &= record(label, False, str(e),
                                     "check NSS/SCK/MOSI/MISO wiring; make sure no other process holds the bus")
                    continue
                all_ok &= record(f"{label}: chip id 0x12", True, "SX1278 responding")
                all_ok &= record(f"radio {name}: RST wire", radio.check_rst_wire(), "",
                                 f"check RST -> GPIO{r['rst_gpio']}")
                all_ok &= record(f"radio {name}: DIO0 wire", radio.check_dio0_wire(), "CadDone seen on DIO0",
                                 f"check DIO0 -> GPIO{r['dio0_gpio']}")
        finally:
            for radio in radios:
                try:
                    radio.close()
                except Exception:
                    pass
            gpio_cleanup()

    for name in active:
        t = _transport(cfg, name)
        if t == "serial":
            all_ok &= check_serial_modem(cfg, name)
        elif t == "bridge":
            all_ok &= check_bridge_modem(cfg, name)
    return all_ok


def main() -> int:
    print("=== pre-flight ===")
    cfg = check_config()
    if cfg is None:
        print(f"\n{RED}pre-flight failed{RESET}")
        return 1
    ok = check_deps(cfg)
    ok &= check_spi_nodes(cfg)
    ok &= check_groups(cfg)
    ok &= check_bluetooth(cfg)
    ok &= check_radios(cfg)

    failed = [l for l, good, _ in results if not good]
    print()
    if failed:
        print(f"{RED}pre-flight FAILED{RESET} — {len(failed)} check(s): {', '.join(failed)}")
        return 1
    print(f"{GREEN}pre-flight OK{RESET} — {len(results)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
