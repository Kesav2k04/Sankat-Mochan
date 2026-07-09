#!/usr/bin/env python3
"""
Pre-flight: everything that must be true before the gateway can work.

Checks the config, the Python deps, the SPI device nodes, the Bluetooth adapter, and
then talks to both radios for real — chip ID, MOSI/MISO write-read-back, the RST wire
and the DIO0 interrupt wire. No transmit, so it is safe with or without antennas.

Exit 0 = go. Exit 1 = something is wrong, and it says which and how to fix it.
"""
from __future__ import annotations

import grp
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


def check_deps() -> bool:
    missing = []
    for mod in ("spidev", "RPi.GPIO", "bleak", "requests"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return record(
        "python deps installed", not missing,
        "spidev, RPi.GPIO, bleak, requests" if not missing else f"missing: {', '.join(missing)}",
        "run.sh recreates the venv: rm -rf ../.venv && ./run.sh check",
    )


def check_config():
    try:
        import config
        cfg = config.load()
        import config as c
        lc = c.lora_config(cfg)
    except Exception as e:
        record("config loads and validates", False, str(e),
               "check gateway/config.json and any SANKAT_* env vars")
        return None
    record("config loads and validates", True,
           f"{lc.frequency_hz/1e6:.3f} MHz SF{lc.spreading_factor} "
           f"BW{lc.bandwidth_hz//1000}k {lc.tx_power_dbm} dBm")
    return cfg


def check_spi_nodes(cfg) -> bool:
    bus = cfg["lora"]["spi"]["bus"]
    needed = [f"/dev/spidev{bus}.{cfg['radios'][n]['cs']}" for n in ("field", "gateway")]
    missing = [p for p in needed if not Path(p).exists()]
    return record(
        "SPI device nodes present", not missing,
        " ".join(needed) if not missing else f"missing: {' '.join(missing)}",
        "sudo raspi-config nonint do_spi 0 && sudo reboot",
    )


def check_groups() -> bool:
    if os.geteuid() == 0:
        return record("user in spi + gpio groups", True, "running as root")
    mine = {grp.getgrgid(g).gr_name for g in os.getgroups()}
    missing = {"spi", "gpio"} - mine
    return record("user in spi + gpio groups", not missing,
                  "spi, gpio" if not missing else f"missing: {', '.join(sorted(missing))}",
                  f"sudo usermod -aG {','.join(sorted(missing))} $USER  # then log out and back in")


def check_bluetooth(cfg) -> bool:
    if not cfg["ble"]["enabled"]:
        return record("bluetooth adapter", True, "ble.enabled=false, skipped")
    try:
        out = subprocess.run(["rfkill", "list", "bluetooth"], capture_output=True, text=True, timeout=5).stdout
    except Exception as e:
        return record("bluetooth adapter", False, str(e), "is `rfkill` installed?")
    if not out.strip():
        return record("bluetooth adapter", False, "no adapter found", "check the Pi's onboard BT")
    if "Soft blocked: yes" in out:
        return record("bluetooth adapter", False, "soft-blocked",
                      "sudo rfkill unblock bluetooth   (run.sh does this for you)")
    if "Hard blocked: yes" in out:
        return record("bluetooth adapter", False, "hard-blocked", "check a physical switch / firmware")
    up = Path("/sys/class/bluetooth/hci0").exists()
    return record("bluetooth adapter", up, "hci0 unblocked" if up else "hci0 absent",
                  "sudo hciconfig hci0 up")


def check_radios(cfg) -> bool:
    import config as c
    from sx127x import Radio, gpio_cleanup, gpio_init

    lora_cfg = c.lora_config(cfg)
    gpio_init()
    all_ok = True
    radios = []
    try:
        for name in ("field", "gateway"):
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
    return all_ok


def main() -> int:
    print("=== pre-flight ===")
    ok = check_deps()
    cfg = check_config()
    if cfg is None:
        print(f"\n{RED}pre-flight failed{RESET}")
        return 1
    ok &= check_spi_nodes(cfg)
    ok &= check_groups()
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
